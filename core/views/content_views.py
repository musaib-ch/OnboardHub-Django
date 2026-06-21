"""Content modules (Knowledge / Training / Orientation / Presentations).

All driven by the `Content` table (kind-differentiated) + `Engagement` for
per-employee completion. No new tables.
"""
from django.http import Http404, JsonResponse
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from ..decorators import login_required, roles_required
from ..models import Content, Engagement
from ..services import log_activity

CONTENT_KINDS = {
    "knowledge":   {"label": "Knowledge Hub",  "icon": "bi-journal-bookmark", "completable": False, "noun": "article"},
    "training":    {"label": "Training",       "icon": "bi-mortarboard",      "completable": True,  "noun": "module"},
    "orientation": {"label": "Orientation",    "icon": "bi-compass",          "completable": True,  "noun": "session"},
    "presentation":{"label": "Presentations",  "icon": "bi-easel2",           "completable": False, "noun": "presentation"},
}


def _cfg(kind):
    cfg = CONTENT_KINDS.get(kind)
    if not cfg:
        raise Http404("Unknown content type")
    return cfg


# ── Admin: manage content of a kind ──────────────────────────────────────────
@roles_required("super_admin", "admin", "hrbp")
@require_http_methods(["GET", "POST"])
def manage(request, kind):
    cfg = _cfg(kind)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            Content.objects.filter(id=request.POST.get("item_id"), kind=kind).delete()
            messages.success(request, f"{cfg['noun'].title()} deleted.")
        elif action == "toggle":
            c = Content.objects.filter(id=request.POST.get("item_id"), kind=kind).first()
            if c:
                c.is_active = not c.is_active
                c.save(update_fields=["is_active"])
        elif action == "reorder":
            ids = [i for i in (request.POST.get("order") or "").split(",") if i.isdigit()]
            for idx, cid in enumerate(ids):
                Content.objects.filter(id=cid, kind=kind).update(display_order=idx)
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": True})
            messages.success(request, "Order updated.")
        else:  # add or edit
            item_id = request.POST.get("item_id")
            obj = (Content.objects.filter(id=item_id, kind=kind).first()
                   if item_id else None) or Content(kind=kind, tenant=request.user.tenant,
                                                     created_by=request.user)
            obj.title = (request.POST.get("title") or "Untitled").strip()
            obj.category = (request.POST.get("category") or "").strip()
            obj.body = request.POST.get("body") or ""
            meta = dict(obj.meta or {})
            video_url = (request.POST.get("video_url") or "").strip()
            if video_url:
                meta["video_url"] = video_url
            else:
                meta.pop("video_url", None)
            obj.meta = meta
            try:
                obj.display_order = int(request.POST.get("display_order") or 0)
            except ValueError:
                obj.display_order = 0
            if request.POST.get("remove_file") and obj.file:
                obj.file.delete(save=False)
                obj.file = None
            if request.FILES.get("file"):
                obj.file = request.FILES["file"]
            # "Publish" makes it visible to employees; "Save as draft" hides it.
            obj.is_active = request.POST.get("is_active") == "1"
            obj.save()
            messages.success(
                request,
                f"{cfg['noun'].title()} {'updated' if item_id else 'created'}"
                + ("." if obj.is_active else " as a draft."))
        return redirect("content_manage", kind=kind)

    items = list(Content.objects.filter(kind=kind).order_by("display_order", "-created_at"))
    items_json = [{
        "id": i.id, "title": i.title, "category": i.category or "",
        "body": i.body or "", "video_url": (i.meta or {}).get("video_url", ""),
        "is_active": i.is_active,
        "file_name": (i.file.name.rsplit("/", 1)[-1] if i.file else ""),
    } for i in items]
    return render(request, "admin/content_manage.html", {
        "kind": kind, "cfg": cfg, "items": items, "items_json": items_json,
        "published": sum(1 for i in items if i.is_active),
    })


# ── Employee: browse + read + complete ───────────────────────────────────────
@login_required
def browse(request, kind):
    cfg = _cfg(kind)
    items = list(Content.objects.filter(kind=kind, is_active=True)
                 .order_by("category", "display_order", "-created_at"))
    done = set(Engagement.objects.filter(
        user=request.user, content__in=items, status="completed"
    ).values_list("content_id", flat=True))
    # group by category for display
    categories = {}
    for it in items:
        categories.setdefault(it.category or "General", []).append(it)
    return render(request, "employee/content_list.html", {
        "kind": kind, "cfg": cfg, "items": items, "done": done,
        "categories": categories,
        "total": len(items), "done_count": len(done),
    })


@login_required
@require_http_methods(["GET", "POST"])
def read(request, item_id):
    item = get_object_or_404(Content, id=item_id, is_active=True)
    cfg = _cfg(item.kind)
    eng = Engagement.objects.filter(user=request.user, content=item).first()
    if request.method == "POST" and request.POST.get("action") == "complete" and cfg["completable"]:
        if not eng:
            eng = Engagement(user=request.user, content=item, kind="enrollment",
                             tenant=request.user.tenant)
        eng.status = "completed"
        eng.progress = 100
        eng.completed_at = timezone.now()
        eng.title = item.title
        eng.save()
        log_activity(request, action="complete_content", entity_type=item.kind,
                     entity_id=item.id, description=f"Completed {item.title}")
        messages.success(request, f"Marked “{item.title}” as complete.")
        return redirect("content_read", item_id=item.id)
    ext = (item.file.name.rsplit(".", 1)[-1].lower() if item.file else "")
    return render(request, "employee/content_detail.html", {
        "item": item, "cfg": cfg, "eng": eng,
        "is_pdf": ext == "pdf",
        "is_image": ext in ("png", "jpg", "jpeg", "gif", "webp"),
    })
