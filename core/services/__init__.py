"""Shared helpers: feature flags, onboarding progress, activity logging, notifications."""
from django.utils import timezone

from ..models import AppSetting, AuditLog, Notification, Form, FormResponse, OnboardingDocument


# ── Stage / feature flags ────────────────────────────────────────────────────
def stage_flags():
    def on(key, default="true"):
        return (AppSetting.get(key, default) or default).lower() == "true"
    return {
        "medical_enabled": on("stage_medical_enabled"),
        "pre_onboarding_enabled": on("stage_pre_onboarding_enabled"),
        "offer_enabled": on("stage_offer_enabled"),
        "onboarding_enabled": on("stage_onboarding_enabled"),
        "post_onboarding_enabled": on("stage_post_onboarding_enabled"),
        "learning_enabled": on("feature_learning"),
    }


def feature_enabled(key):
    # In this rebuild all features default on; a tenant or AppSetting may disable.
    val = AppSetting.get(f"feature_{key}", None)
    if val is not None:
        return val.lower() == "true"
    return True


# ── Onboarding progress (ported from inject_site_settings) ───────────────────
PROGRESS_MAP = {
    "pending": 5,
    "medical_upload": 10, "medical_under_review": 20, "medical_info_requested": 20,
    "medical_resubmission": 15, "medical_rejected": 5,
    "pre_onboarding": 40, "pre_onboarding_resubmission": 40,
    "pre_onboarding_info_requested": 40, "pre_onboarding_submitted": 55,
    "pre_onboarding_rejected": 35,
    "offer": 55, "offer_submitted": 65,
    "onboarding": 75, "post_onboarding": 90, "completed": 100,
}


def onboarding_progress_percent(status=None, user=None):
    status_value = (status or "").strip().lower()
    if user is None or getattr(user, "role", None) != "employee":
        return PROGRESS_MAP.get(status_value, 5)
    if not status_value:
        status_value = (getattr(user, "status", "") or "").strip().lower()
    if status_value == "completed":
        return 100

    flags = stage_flags()

    def stage_completion_ratio(stage_key):
        forms = Form.objects.filter(stage=stage_key, is_active=True).filter(
            models_q_employee_type(user)
        )
        required_names = []
        for f in forms:
            required_names.extend(f.required_field_names())
        form_ratio = None
        if required_names:
            answered = 0
            responses = FormResponse.objects.filter(
                employee=user, form__stage=stage_key, is_draft=False
            )
            answered_names = set()
            for r in responses:
                answered_names.update(
                    k for k, v in (r.answers or {}).items() if v not in (None, "", [])
                )
            answered = len(set(required_names) & answered_names)
            form_ratio = answered / max(len(set(required_names)), 1)

        req_docs = OnboardingDocument.objects.filter(
            stage=stage_key, is_active=True, is_required=True
        )
        docs_ratio = None
        if req_docs.exists():
            signed = sum(1 for d in req_docs if d.signed_by(user.id))
            docs_ratio = signed / max(req_docs.count(), 1)

        parts = [p for p in (form_ratio, docs_ratio) if p is not None]
        return 1.0 if not parts else max(0.0, min(1.0, sum(parts) / len(parts)))

    ratios = []
    if flags["medical_enabled"]:
        done_states = {
            "pre_onboarding", "pre_onboarding_submitted", "pre_onboarding_resubmission",
            "pre_onboarding_info_requested", "pre_onboarding_rejected",
            "onboarding", "post_onboarding", "completed",
        }
        ratios.append(1.0 if status_value in done_states else 0.5
                      if status_value.startswith("medical") else 0.0)
    if flags["pre_onboarding_enabled"]:
        if status_value in {"pre_onboarding_submitted", "onboarding", "post_onboarding", "completed"}:
            ratios.append(1.0)
        elif status_value in {"pre_onboarding", "pre_onboarding_resubmission",
                              "pre_onboarding_info_requested", "pre_onboarding_rejected"}:
            ratios.append(stage_completion_ratio("pre_onboarding"))
        else:
            ratios.append(0.0)
    if flags["onboarding_enabled"]:
        if status_value in {"post_onboarding", "completed"}:
            ratios.append(1.0)
        elif status_value == "onboarding":
            ratios.append(stage_completion_ratio("onboarding"))
        else:
            ratios.append(0.0)
    if flags["post_onboarding_enabled"]:
        ratios.append(1.0 if status_value == "completed"
                      else stage_completion_ratio("post_onboarding")
                      if status_value == "post_onboarding" else 0.0)

    if not ratios:
        return PROGRESS_MAP.get(status_value, 5)
    pct = int(round((sum(ratios) / len(ratios)) * 100))
    return max(5 if status_value else 0, min(100, pct))


def models_q_employee_type(user):
    """Forms that apply to this employee's type (or to everyone)."""
    from django.db.models import Q
    et = getattr(user, "employee_type", None)
    return Q(employee_type__isnull=True) | Q(employee_type="") | Q(employee_type=et)


# ── Activity logging + notifications ─────────────────────────────────────────
def log_activity(request=None, user=None, action="", entity_type=None, entity_id=None,
                 description=""):
    ip = None
    if request is not None:
        ip = request.META.get("REMOTE_ADDR")
        if user is None and getattr(request, "user", None) and request.user.is_authenticated:
            user = request.user
    AuditLog.objects.create(
        user=user if (user and user.is_authenticated) else None,
        action=action, entity_type=entity_type, entity_id=entity_id,
        description=description, ip_address=ip, timestamp=timezone.now(),
    )


def notify(user, title, message="", link=None, category="info"):
    if not user or not user.enable_in_app_notifications:
        return None
    note = Notification.objects.create(
        user=user, title=title, message=message, link=link, category=category
    )
    # Best-effort email copy, sent in the background so the request doesn't block.
    try:
        from ..email_service import smtp_configured, send_email_async
        if user.enable_email_notifications and smtp_configured():
            def _mark(ok, err, note_id=note.id):
                Notification.objects.filter(id=note_id).update(
                    email_sent=ok, email_error=None if ok else (err or "")[:500],
                )
            send_email_async(user.email, title, message or title, on_sent=_mark)
    except Exception:
        pass
    return note
