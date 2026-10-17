"""Content modules (Knowledge / Training / Orientation / Presentations).

All driven by the `Content` table (kind-differentiated) + `Engagement` for
per-employee completion. No new tables.
"""
from django.http import Http404, JsonResponse
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .. import pipeline
from ..decorators import login_required, roles_required
from ..models import Content, Engagement
from ..services import log_activity

SUPPORTED_CONTENT_EXTENSIONS = {
    "document": ["pdf", "doc", "docx", "ppt", "pptx", "txt", "rtf"],
    "scorm": ["zip", "scorm", "scorm.zip"],
}


def _guess_asset_type(file_name):
    if not file_name:
        return "document"
    ext = file_name.rsplit(".", 1)[-1].lower()
    if ext in SUPPORTED_CONTENT_EXTENSIONS["scorm"]:
        return "scorm"
    if ext in ["ppt", "pptx"]:
        return "presentation"
    return "document"


def _normalize_attach_to(values):
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    return [value for value in values if value in {"onboarding", "post_onboarding", "orientation", "training"}]


def _current_stage_key(user):
    stage = pipeline.current_stage(user)
    if stage:
        return stage
    return pipeline.stage_of_status(getattr(user, "status", None))


def _is_content_visible_to_user(user, item):
    attach_to = (item.meta or {}).get("attach_to") or []
    if not attach_to:
        return True
    current_stage = _current_stage_key(user)
    return bool(current_stage and current_stage in attach_to)


CONTENT_KINDS = {
    "knowledge":     {"label": "Knowledge Hub",  "icon": "bi-journal-bookmark", "completable": False, "noun": "article"},
    "training":      {"label": "Training",       "icon": "bi-mortarboard",      "completable": True,  "noun": "module"},
    "orientation":   {"label": "Orientation",    "icon": "bi-compass",          "completable": True,  "noun": "session"},
    "presentation":  {"label": "Presentations",  "icon": "bi-easel2",           "completable": False, "noun": "presentation"},
    "learning_path": {"label": "Learning Paths", "icon": "bi-signpost-split",   "completable": True,  "noun": "path"},
}

KIND_ALIASES = {
    "learning_paths": "learning_path",
    "learning-paths": "learning_path",
    "learningpath": "learning_path",
    "learning": "training",
}


def _cfg(kind):
    target_kind = KIND_ALIASES.get(kind, kind)
    cfg = CONTENT_KINDS.get(target_kind)
    if not cfg:
        raise Http404(f"Unknown content type '{kind}'")
    return cfg


# ── Admin: manage content of a kind ──────────────────────────────────────────
@roles_required("super_admin", "admin", "hrbp")
@require_http_methods(["GET", "POST"])
def manage(request, kind):
    cfg = _cfg(kind)
    hrbp_depts = (request.user.scope or {}).get("departments") or [] if request.user.role == "hrbp" else []

    if request.method == "POST":
        action = request.POST.get("action")
        if action != "reorder" and request.user.role == "hrbp":
            messages.error(request, "You do not have permission to modify library items.")
            return redirect("content_manage", kind=kind)
        if action == "delete":
            item_id = request.POST.get("item_id")
            c = Content.objects.filter(id=item_id, kind=kind).first()
            if c:
                if request.user.role == "hrbp" and kind == "training" and c.target_departments:
                    if not any(int(tid) in hrbp_depts for tid in c.target_departments if str(tid).isdigit() or isinstance(tid, int)):
                        messages.error(request, "This module is outside your scope.")
                        return redirect("content_manage", kind=kind)
                c.delete()
                messages.success(request, f"{cfg['noun'].title()} deleted.")
        elif action == "toggle":
            item_id = request.POST.get("item_id")
            c = Content.objects.filter(id=item_id, kind=kind).first()
            if c:
                if request.user.role == "hrbp" and kind == "training" and c.target_departments:
                    if not any(int(tid) in hrbp_depts for tid in c.target_departments if str(tid).isdigit() or isinstance(tid, int)):
                        messages.error(request, "This module is outside your scope.")
                        return redirect("content_manage", kind=kind)
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
            obj = None
            if item_id:
                obj = Content.objects.filter(id=item_id, kind=kind).first()
                if obj and request.user.role == "hrbp" and kind == "training" and obj.target_departments:
                    if not any(int(tid) in hrbp_depts for tid in obj.target_departments if str(tid).isdigit() or isinstance(tid, int)):
                        messages.error(request, "This module is outside your scope.")
                        return redirect("content_manage", kind=kind)
            if not obj:
                obj = Content(kind=kind, tenant=request.user.tenant, created_by=request.user)
                if request.user.role == "hrbp" and kind == "training":
                    obj.target_departments = hrbp_depts
            obj.title = (request.POST.get("title") or "Untitled").strip()
            obj.category = (request.POST.get("category") or "").strip()
            obj.body = request.POST.get("body") or ""
            meta = dict(obj.meta or {})
            video_url = (request.POST.get("video_url") or "").strip()
            if video_url:
                meta["video_url"] = video_url
            else:
                meta.pop("video_url", None)
            asset_type = request.POST.get("asset_type") or "document"
            if request.FILES.get("file"):
                asset_type = _guess_asset_type(request.FILES["file"].name)
            meta["asset_type"] = asset_type
            meta["launch_mode"] = request.POST.get("launch_mode") or ("launch" if asset_type == "scorm" else "download")
            meta["attach_to"] = _normalize_attach_to(request.POST.getlist("attach_to"))

            # Enterprise Orientation fields
            if kind == "orientation":
                meta["presenter_name"] = (request.POST.get("presenter_name") or "").strip()
                meta["meeting_url"] = (request.POST.get("meeting_url") or "").strip()
                meta["event_datetime"] = (request.POST.get("event_datetime") or "").strip()
                meta["location"] = (request.POST.get("location") or "Virtual / Live Room").strip()
                meta["capacity"] = (request.POST.get("capacity") or "50").strip()

            # Enterprise Learning Path modules
            if kind in ("training", "learning_path"):
                modules_raw = request.POST.getlist("module_titles")
                modules_desc = request.POST.getlist("module_descriptions")
                modules = []
                for idx, m_title in enumerate(modules_raw):
                    m_title = m_title.strip()
                    if m_title:
                        m_desc = modules_desc[idx].strip() if idx < len(modules_desc) else ""
                        modules.append({"id": f"mod_{idx+1}", "title": m_title, "desc": m_desc, "duration": 15})
                meta["modules"] = modules

            obj.meta = meta
            if kind == "training":
                t_depts = []
                for val in request.POST.getlist("target_departments"):
                    val = val.strip()
                    if val.isdigit():
                        t_depts.append(int(val))
                if request.user.role == "hrbp":
                    t_depts = [tid for tid in t_depts if int(tid) in hrbp_depts]
                    if not t_depts:
                        t_depts = hrbp_depts
                obj.target_departments = t_depts
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

    items_qs = Content.objects.filter(kind=kind).order_by("display_order", "-created_at")
    items = []
    for i in items_qs:
        if request.user.role == "hrbp" and kind == "training":
            t_depts = i.target_departments or []
            if t_depts and not any(int(tid) in hrbp_depts for tid in t_depts if str(tid).isdigit() or isinstance(tid, int)):
                continue
        items.append(i)

    from ..models import OrgUnit
    depts_map = {d.id: d.name for d in OrgUnit.objects.filter(kind="department", is_active=True)}
    for i in items:
        t_ids = i.target_departments or []
        i.target_dept_names = ", ".join([depts_map.get(int(tid), str(tid)) for tid in t_ids if str(tid).isdigit() or isinstance(tid, int)]) or "Global / All"

    items_json = [{
        "id": i.id, "title": i.title, "category": i.category or "",
        "body": i.body or "", "video_url": (i.meta or {}).get("video_url", ""),
        "asset_type": (i.meta or {}).get("asset_type", "document"),
        "launch_mode": (i.meta or {}).get("launch_mode", "download"),
        "attach_to": (i.meta or {}).get("attach_to", []),
        "presenter_name": (i.meta or {}).get("presenter_name", ""),
        "meeting_url": (i.meta or {}).get("meeting_url", ""),
        "event_datetime": (i.meta or {}).get("event_datetime", ""),
        "location": (i.meta or {}).get("location", ""),
        "modules": (i.meta or {}).get("modules", []),
        "is_active": i.is_active,
        "file_name": (i.file.name.rsplit("/", 1)[-1] if i.file else ""),
        "target_departments": i.target_departments or [],
    } for i in items]

    depts = OrgUnit.objects.filter(kind="department", is_active=True)
    if request.user.role == "hrbp":
        depts = depts.filter(id__in=hrbp_depts)

    return render(request, "admin/content_manage.html", {
        "kind": kind, "cfg": cfg, "items": items, "items_json": items_json,
        "published": sum(1 for i in items if i.is_active),
        "departments": depts,
    })


# ── Employee: browse + read + complete ───────────────────────────────────────
@login_required
def browse(request, kind):
    cfg = _cfg(kind)
    items = [
        item for item in Content.objects.filter(kind=kind, is_active=True)
        .order_by("category", "display_order", "-created_at")
        if _is_content_visible_to_user(request.user, item)
    ]
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
    if not _is_content_visible_to_user(request.user, item):
        raise Http404("This content is not available for your current stage")
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
    asset_type = (item.meta or {}).get("asset_type") or _guess_asset_type(item.file.name if item.file else "")
    launch_mode = (item.meta or {}).get("launch_mode") or ("launch" if asset_type == "scorm" else "download")
    return render(request, "employee/content_detail.html", {
        "item": item, "cfg": cfg, "eng": eng,
        "is_pdf": ext == "pdf",
        "is_image": ext in ("png", "jpg", "jpeg", "gif", "webp"),
        "asset_type": asset_type,
        "launch_mode": launch_mode,
    })


@login_required
def orientation_ics_export(request, item_id):
    """Generate downloadable .ics iCalendar file for orientation events."""
    from django.http import HttpResponse
    item = get_object_or_404(Content, id=item_id)
    meta = item.meta or {}
    title = item.title
    desc = (item.body or "").replace("\n", " ")
    now_str = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    
    ics_content = f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//OnboardHub//Orientation Calendar 1.0//EN\r\nBEGIN:VEVENT\r\nUID:orientation-{item.id}@onboardhub.com\r\nDTSTAMP:{now_str}\r\nSUMMARY:{title}\r\nDESCRIPTION:{desc}\r\nLOCATION:{(meta.get('video_url') or 'Online Orientation')}\r\nEND:VEVENT\r\nEND:VCALENDAR"

    response = HttpResponse(ics_content, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="orientation_{item.id}.ics"'
    return response
