<<<<<<< HEAD
from django.db.models import Q
=======
>>>>>>> origin/main
from django.http import JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

<<<<<<< HEAD
from ..models import Content, Notification, User
=======
from ..models import Notification
>>>>>>> origin/main
from ..decorators import login_required
from ..permissions import is_employee_role


@login_required
def index(request):
    """Post-login dispatcher (mirrors Flask `index`)."""
    user = request.user
    if is_employee_role(user.role):
        if not user.date_of_joining and user.status not in ("pending", "on_hold"):
            return redirect("employee_set_joining_date")
    # All users land on portal first
    return redirect("portal")


@login_required
def portal(request):
    """Distinctive landing: an onboarding-journey view for employees, a quick
    launchpad for staff. Shown first (welcome) and via the Home link."""
    from .. import pipeline
    from ..services import onboarding_progress_percent

    user = request.user
    first_visit = not user.has_seen_welcome
    if first_visit:
        user.has_seen_welcome = True
        user.save(update_fields=["has_seen_welcome"])

    hour = timezone.localtime(timezone.now()).hour
    greeting = ("Good morning" if hour < 12 else
                "Good afternoon" if hour < 17 else "Good evening")

<<<<<<< HEAD
    def active(kind):
        return _visible_portal_content(user, [kind])
=======
    from ..models import Content

    def active(kind):
        return list(Content.objects.filter(kind=kind, is_active=True).order_by("display_order", "-created_at"))
>>>>>>> origin/main

    cms = {
        "sliders": active("portal_slider"),
        "messages": active("management_message"),
        "gallery": active("portal_gallery"),
        "videos": active("portal_video"),
<<<<<<< HEAD
        "resources": active("portal_resource"),
        "news": active("news"),
        "events": active("event"),
    }
    cms["toolkit_resources"] = [
        item for item in cms["resources"]
        if (item.category or "").strip().lower() in {"toolkit", "quick link", "quick links"}
    ]
    cms["principles"] = [
        item for item in cms["resources"]
        if (item.category or "").strip().lower() in {"principle", "principles", "working together"}
    ]
=======
        "news": active("news"),
        "events": active("event"),
    }
>>>>>>> origin/main
    cms["has_any"] = any(v for k, v in cms.items() if k != "has_any")

    # Employees always see their onboarding journey; staff always see the launchpad.
    is_employee = is_employee_role(user.role)
    show_journey = is_employee
    show_launchpad = not is_employee

    ctx = {
        "first_visit": first_visit, "greeting": greeting, "cms": cms,
        "is_employee": is_employee, "show_journey": show_journey,
        "show_launchpad": show_launchpad, "position": user.position_title,
    }

    if show_journey:
        stage_url = {
            "offer": "my_offers",
            "medical": "employee_medical",
            "pre_onboarding": "employee_pre_onboarding",
            "onboarding": "employee_onboarding",
            "post_onboarding": "employee_post_onboarding",
        }
        stage_icon = {
            "offer": "bi-envelope-paper-heart",
            "medical": "bi-heart-pulse",
            "pre_onboarding": "bi-file-earmark-text",
            "onboarding": "bi-folder-check",
            "post_onboarding": "bi-check2-square",
        }
        stage_path = [s for s in pipeline.get_employee_stage_path(user) if s in stage_url]
        if not stage_path:
            stage_path = pipeline.enabled_stages()
        steps = [{
            "key": s, "label": pipeline.STAGE_LABELS[s],
            "state": pipeline.stage_state(user, s),
            "url_name": stage_url[s], "icon": stage_icon[s],
        } for s in stage_path]
        pct = onboarding_progress_percent(user.status, user)
        cur = pipeline.current_stage(user)
        total = len(steps)
        done = sum(1 for s in steps if s["state"] == "completed")
        if user.status == "completed":
            step_num = total
        else:
            step_num = (stage_path.index(cur) + 1) if cur in stage_path else total
        ctx.update({
            "pct": pct,
            "ring_offset": round(377 * (1 - pct / 100)),  # 2*pi*60 ≈ 377
            "steps": steps,
            "total_steps": total,
            "step_num": step_num,
            "journey_fill": round(done / (total - 1) * 100) if total > 1 else 0,
            "current_stage": cur,
            "current_label": pipeline.STAGE_LABELS.get(cur, ""),
            "current_url": stage_url.get(cur, "employee_home"),
            "completed": user.status == "completed",
            "stage_path": stage_path,
        })
    return render(request, "portal/landing.html", ctx)


@login_required
<<<<<<< HEAD
def employee_directory(request):
    """Read-only directory limited to the current tenant's active employees."""
    people = User.objects.none()
    if request.user.tenant_id:
        people = (User.objects.filter(
            tenant_id=request.user.tenant_id,
            role="employee",
            is_active=True,
        ).exclude(status="deleted").select_related("department").order_by("full_name", "email"))
    return render(request, "portal/employee_directory.html", {"people": people})


def _visible_portal_content(user, kinds):
    query = Content.objects.filter(kind__in=kinds, is_active=True)
    if user.tenant_id:
        query = query.filter(Q(tenant_id=user.tenant_id) | Q(tenant__isnull=True))
    else:
        query = query.filter(tenant__isnull=True)

    from .content_views import _is_content_visible_to_user
    visible = []
    for item in query.order_by("display_order", "-created_at"):
        roles = item.target_roles or []
        departments = [str(value) for value in (item.target_departments or [])]
        if roles and user.role not in roles:
            continue
        if departments and str(user.department_id or "") not in departments:
            continue
        if _is_content_visible_to_user(user, item):
            visible.append(item)
    return visible


@login_required
def employee_resources(request):
    """Show tenant CMS resources, announcements, and orientation events."""
    all_resources = _visible_portal_content(request.user, ["portal_resource"])
    privacy_resources = [
        item for item in all_resources
        if "privacy" in (item.category or "").lower()
        or "privacy" in item.title.lower()
        or (item.meta or {}).get("section") == "privacy"
    ]
    security_resources = [
        item for item in all_resources
        if "security" in (item.category or "").lower()
        or "security" in item.title.lower()
        or (item.meta or {}).get("section") == "security"
    ]
    resources = [
        item for item in all_resources
        if (item.category or "").strip().lower() not in {
            "toolkit", "quick link", "quick links", "principle", "principles", "working together",
        }
    ]
    return render(request, "portal/employee_resources.html", {
        "resources": resources,
        "privacy_resources": privacy_resources,
        "security_resources": security_resources,
        "news": _visible_portal_content(request.user, ["news"]),
        "events": _visible_portal_content(request.user, ["event"]),
        "support_email": "support@onboardhub.local",
    })


@login_required
=======
>>>>>>> origin/main
def document_view(request, doc_id):
    """Inline viewer for an onboarding document (renders body HTML or embeds the file)."""
    from ..models import OnboardingDocument
    from .. import pipeline
    doc = get_object_or_404(OnboardingDocument, id=doc_id, is_active=True)
    user = request.user
    ext = (doc.file.name.rsplit(".", 1)[-1].lower() if doc.file else "")
    signed = doc.signed_by(user.id)
    can_sign = (is_employee_role(user.role) and pipeline.is_editable(user, doc.stage)
                and not signed)
    return render(request, "document_viewer.html", {
        "doc": doc, "ext": ext, "signed": signed, "can_sign": can_sign,
        "is_pdf": ext == "pdf",
        "is_image": ext in ("png", "jpg", "jpeg", "gif", "webp"),
    })


@login_required
@require_POST
def document_sign(request, doc_id):
    from ..models import OnboardingDocument
    from .. import pipeline
    from ..services import log_activity
    doc = get_object_or_404(OnboardingDocument, id=doc_id, is_active=True)
    user = request.user
    if not is_employee_role(user.role) or not pipeline.is_editable(user, doc.stage):
        return redirect("document_view", doc_id=doc.id)
    if not doc.signed_by(user.id):
        doc.signatures.append({"employee_id": user.id, "signed_at": timezone.now().isoformat()})
        doc.save(update_fields=["signatures"])
        log_activity(request, action="sign_document", entity_type="document",
                     entity_id=doc.id, description=f"Signed {doc.title}")
        from django.contrib import messages
        messages.success(request, f"You signed “{doc.title}”.")
    return redirect("document_view", doc_id=doc.id)


@login_required
def notifications_list(request):
    notes = Notification.objects.filter(user=request.user)
    return render(request, "notifications/list.html", {"notifications": notes})


@login_required
def notifications_feed(request):
    """JSON feed for the live bell dropdown."""
    qs = Notification.objects.filter(user=request.user)
    items = [{
        "id": n.id,
        "title": n.title,
        "message": n.message or "",
        "link": n.link or "",
        "category": n.category,
        "is_read": n.is_read,
        "created_at": timezone.localtime(n.created_at).strftime("%d %b, %H:%M"),
    } for n in qs[:15]]
    return JsonResponse({
        "unread": qs.filter(is_read=False).count(),
        "items": items,
    })


@login_required
@require_POST
def notification_mark_read(request, notif_id):
    note = get_object_or_404(Notification, id=notif_id, user=request.user)
    note.is_read = True
    note.save(update_fields=["is_read"])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def notifications_mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect("notifications_list")


@login_required
@require_POST
def notifications_clear(request):
    Notification.objects.filter(user=request.user).delete()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect("notifications_list")
