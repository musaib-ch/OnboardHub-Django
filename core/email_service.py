"""Email service for the main OnboardHub portal.

Main-portal email prefers Gmail API over HTTPS when Gmail OAuth is configured.
SMTP remains available as a fallback for environments that still permit SMTP.
The Gmail path is used for employee creation, welcome emails, password reset,
and portal notifications without requiring SMTP ports 25/465/587.
"""
import threading

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import connections

from .models import AppSetting


def email_provider():
    """Return the active main-portal email transport."""
    try:
        from .gmail_service import configured as gmail_configured
        if gmail_configured():
            return "gmail_api"
    except Exception:
        pass
    return "smtp"


def smtp_configured():
    """Return True when the legacy SMTP host is configured."""
    return bool((AppSetting.get("smtp_host") or "").strip())


def gmail_configured():
    try:
        from .gmail_service import configured as _configured
        return bool(_configured())
    except Exception:
        return False


def email_configured():
    return gmail_configured() or smtp_configured()


def _clean(value):
    return (value or "").replace("\ufeff", "").strip().strip('"\'')


def from_address():
    if gmail_configured():
        try:
            from .gmail_service import account_email, sender_name
            email = _clean(account_email())
            if email:
                return f"{sender_name()} <{email}>"
        except Exception:
            pass
    name = _clean(AppSetting.get("smtp_from_name") or "OnboardHub")
    email = _clean(AppSetting.get("smtp_from_email") or AppSetting.get("smtp_user") or "noreply@onboardhub.local")
    return f"{name} <{email}>"


def _connection():
    """Return the AppSetting-backed resilient SMTP backend."""
    return get_connection(
        backend="core.db_email_backend.AppSettingEmailBackend",
        fail_silently=False,
    )


def _audit_email(to, subject, ok, error=None, provider=None, message_id=None):
    try:
        from .services import log_activity
        recipients = [to] if isinstance(to, str) else list(to)
        provider = provider or email_provider()
        detail = (
            f"Email {'accepted' if ok else 'failed'} via {provider}; "
            f"to={', '.join(recipients)}; subject={subject!r}"
        )
        if message_id:
            detail += f"; message_id={message_id}"
        if error:
            detail += f"; error={error}"
        log_activity(
            action="email_sent" if ok else "email_failed",
            entity_type="email",
            description=detail,
        )
    except Exception:
        pass


# ── Editable email templates (stored in AppSetting JSON) ─────────────────────
EMAIL_TEMPLATE_DEFAULTS = {
    "password_reset": {
        "label": "Password reset",
        "subject": "Reset your OnboardHub password",
        "body": "Hello {full_name},\n\nWe received a request to reset your password. "
                "Open this link to choose a new one (valid for 1 hour):\n\n{link}\n\n"
                "If you didn't request this, you can ignore this email.",
        "placeholders": ["full_name", "link"],
    },
    "welcome": {
        "label": "Welcome / account created",
        "subject": "Welcome to OnboardHub",
        "body": "Hello {full_name},\n\nYour account has been created. Sign in here:\n{link}",
        "placeholders": ["full_name", "link"],
    },
    "stage_approved": {
        "label": "Stage approved",
        "subject": "Your {stage} was approved",
        "body": "Hello {full_name},\n\nGood news — your {stage} has been approved. "
                "Continue your onboarding here:\n{link}",
        "placeholders": ["full_name", "stage", "link"],
    },
    "stage_action": {
        "label": "Changes / info requested / rejected",
        "subject": "Action needed on your {stage}",
        "body": "Hello {full_name},\n\n{message}\n\nOpen your onboarding:\n{link}",
        "placeholders": ["full_name", "stage", "message", "link"],
    },
    "reminder": {
        "label": "Reminder",
        "subject": "Reminder: {title}",
        "body": "Hello {full_name},\n\n{message}\n\nOpen OnboardHub:\n{link}",
        "placeholders": ["full_name", "title", "message", "link"],
    },
}

EMAIL_TAGS = {
    "full_name": ("Employee's full name", "Demo Employee"),
    "email": ("Employee's email address", "employee@company.com"),
    "employee_id": ("Employee ID", "EMP-0001"),
    "position_title": ("Job title", "Software Engineer"),
    "department": ("Department name", "Engineering"),
    "grade": ("Grade", "M1"),
    "location": ("Location", "Lahore"),
    "payroll": ("Payroll", "Monthly"),
    "employee_type": ("Employee type", "Permanent"),
    "stage": ("Current onboarding stage", "Pre-Onboarding"),
    "status": ("Onboarding status", "Pre Onboarding"),
    "joining_date": ("Date of joining", "01 Jul 2026"),
    "company": ("Company / tenant name", "Demo Company"),
    "link": ("Portal link", "https://portal.example.com/"),
    "title": ("Notification title", "Reminder"),
    "message": ("Free-text message body", "Your message here"),
}

_CUSTOM_EMAIL_KEY = "custom_email_templates"


def get_email_templates():
    import json
    raw = AppSetting.get("email_templates")
    try:
        return json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return {}


def save_email_templates(data, user=None):
    import json
    AppSetting.set("email_templates", json.dumps(data), user=user)


def get_custom_templates():
    import json
    raw = AppSetting.get(_CUSTOM_EMAIL_KEY)
    try:
        data = json.loads(raw) if raw else {}
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def save_custom_templates(data, user=None):
    import json
    AppSetting.set(_CUSTOM_EMAIL_KEY, json.dumps(data), user=user)


def _slug_template_key(value):
    import re
    k = re.sub(r"[^a-z0-9_]+", "_", (value or "").strip().lower())
    return re.sub(r"_+", "_", k).strip("_")[:40]


def all_email_templates():
    overrides = get_email_templates()
    custom = get_custom_templates()
    out = []
    for key, d in EMAIL_TEMPLATE_DEFAULTS.items():
        o = overrides.get(key, {})
        out.append({"key": key, "label": d["label"],
                    "subject": o.get("subject") or d["subject"],
                    "body": o.get("body") or d["body"],
                    "placeholders": d.get("placeholders", []), "custom": False})
    for key, d in custom.items():
        out.append({"key": key, "label": d.get("label") or key,
                    "subject": d.get("subject", ""), "body": d.get("body", ""),
                    "placeholders": d.get("placeholders") or [], "custom": True})
    return out


def upsert_custom_template(key, label, subject, body, user=None):
    import re
    key = _slug_template_key(key or label)
    if not key or key in EMAIL_TEMPLATE_DEFAULTS:
        return None
    placeholders = sorted(set(re.findall(r"\{(\w+)\}", f"{subject or ''} {body or ''}")))
    data = get_custom_templates()
    data[key] = {"label": (label or key.replace("_", " ").title()).strip(),
                 "subject": subject or "", "body": body or "", "placeholders": placeholders}
    save_custom_templates(data, user=user)
    return key


def delete_custom_template(key, user=None):
    data = get_custom_templates()
    if key in data:
        del data[key]
        save_custom_templates(data, user=user)
        return True
    return False


def employee_email_context(emp, link="/employee/home/", message="", title=""):
    return {
        "full_name": emp.full_name or "",
        "email": emp.email or "",
        "employee_id": emp.employee_id or "",
        "position_title": emp.position_title or "",
        "department": emp.department.name if emp.department_id else "",
        "grade": emp.grade or "",
        "location": emp.location_code or "",
        "payroll": emp.payroll or "",
        "employee_type": emp.employee_type or "",
        "stage": (emp.status or "").replace("_", " ").title(),
        "status": (emp.status or "").replace("_", " ").title(),
        "joining_date": emp.date_of_joining.strftime("%d %b %Y") if emp.date_of_joining else "",
        "company": emp.tenant.name if emp.tenant_id else "",
        "link": link, "message": message, "title": title,
    }


def render_email(key, context):
    overrides = get_email_templates().get(key, {})
    custom = get_custom_templates().get(key, {})
    default = EMAIL_TEMPLATE_DEFAULTS.get(key, {})
    subject = (overrides.get("subject") or custom.get("subject") or default.get("subject") or "").strip()
    body = overrides.get("body") or custom.get("body") or default.get("body") or ""
    for k, v in (context or {}).items():
        ph = "{" + k + "}"
        subject = subject.replace(ph, str(v))
        body = body.replace(ph, str(v))
    return subject, body


def send_email(to, subject, body, html=None):
    """Send synchronously through Gmail API or the legacy SMTP fallback."""
    recipients = [to] if isinstance(to, str) else list(to)
    if not recipients:
        return False, "No email recipients were supplied."

    if gmail_configured():
        try:
            from .gmail_service import send_email as gmail_send
            ok, error, message_id = gmail_send(recipients, subject, body, html)
            _audit_email(recipients, subject, ok, error=error, provider="gmail_api", message_id=message_id)
            return ok, error
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            _audit_email(recipients, subject, False, error=error, provider="gmail_api")
            return False, error

    if not smtp_configured():
        return False, "Email is not configured. Connect a Gmail account or configure SMTP."

    try:
        msg = EmailMultiAlternatives(
            subject=subject or "",
            body=body or "",
            from_email=from_address(),
            to=recipients,
            connection=_connection(),
        )
        if html:
            msg.attach_alternative(html, "text/html")
        sent = msg.send(fail_silently=False)
        if sent != 1:
            error = f"SMTP backend did not report delivery (returned {sent})."
            _audit_email(recipients, subject, False, error=error, provider="smtp")
            return False, error
        _audit_email(recipients, subject, True, provider="smtp")
        return True, None
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        _audit_email(recipients, subject, False, error=error, provider="smtp")
        return False, error


def send_email_async(to, subject, body, html=None, on_sent=None):
    """Send in a background thread without losing the actual result."""
    def _run():
        try:
            ok, err = send_email(to, subject, body, html)
            if on_sent:
                try:
                    on_sent(ok, err)
                except Exception:
                    pass
        finally:
            connections.close_all()

    if getattr(settings, "EMAIL_ASYNC", True):
        thread = threading.Thread(target=_run, daemon=True, name="onboardhub-email")
        thread.start()
        return thread
    _run()
    return None
