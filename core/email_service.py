<<<<<<< HEAD
"""SMTP email driven by AppSetting (no settings.py wiring needed).

Settings live in AppSetting keys: smtp_host, smtp_port, smtp_user, smtp_password,
smtp_use_tls, smtp_use_ssl, smtp_from_name, smtp_from_email.

`send_email` is synchronous (returns ok/err). `send_email_async` offloads the
SMTP round-trip to a background thread so web requests don't block on the mail
server. Set settings.EMAIL_ASYNC=False to force synchronous (used in tests).
=======
"""Email service for the main OnboardHub portal.

Main-portal email prefers Gmail API over HTTPS when Gmail OAuth is configured.
SMTP remains available as a fallback for environments that still permit SMTP.
The Gmail path is used for employee creation, welcome emails, password reset,
and portal notifications without requiring SMTP ports 25/465/587.
>>>>>>> origin/main
"""
import threading

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import connections

from .models import AppSetting


<<<<<<< HEAD
def smtp_configured():
    return bool((AppSetting.get("smtp_host") or "").strip())


def _flag(key, default="false"):
    return (AppSetting.get(key, default) or default).strip().lower() == "true"


def from_address():
    name = (AppSetting.get("smtp_from_name") or "OnboardHub").strip()
    email = (AppSetting.get("smtp_from_email") or AppSetting.get("smtp_user")
             or "noreply@onboardhub.local").strip()
=======
def email_provider():
    """Return the active main-portal email transport."""
    return "smtp"


def smtp_configured():
    """Return True when the SMTP host is configured."""
    return bool((AppSetting.get("smtp_host") or "").strip())


def email_configured():
    return smtp_configured()


def _clean(value):
    return (value or "").replace("\ufeff", "").strip().strip('"\'')


def from_address():
    name = _clean(AppSetting.get("smtp_from_name") or "OnboardHub")
    email = _clean(AppSetting.get("smtp_from_email") or AppSetting.get("smtp_user") or "noreply@onboardhub.local")
>>>>>>> origin/main
    return f"{name} <{email}>"


def _connection():
<<<<<<< HEAD
    try:
        port = int(AppSetting.get("smtp_port") or 587)
    except (TypeError, ValueError):
        port = 587
    return get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=(AppSetting.get("smtp_host") or "").strip(),
        port=port,
        username=(AppSetting.get("smtp_user") or "").strip(),
        password=(AppSetting.get("smtp_password") or ""),
        use_tls=_flag("smtp_use_tls", "true"),
        use_ssl=_flag("smtp_use_ssl", "false"),
        timeout=15,
    )


=======
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


>>>>>>> origin/main
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

<<<<<<< HEAD

# Usable tags (placeholder catalog) surfaced in the admin UI + resolvable for sends.
# tag -> (human description, sample value for preview)
=======
>>>>>>> origin/main
EMAIL_TAGS = {
    "full_name": ("Employee's full name", "Demo Employee"),
    "email": ("Employee's email address", "employee@company.com"),
    "employee_id": ("Employee ID", "EMP-0001"),
    "position_title": ("Job title", "Software Engineer"),
    "department": ("Department name", "Engineering"),
<<<<<<< HEAD
=======
    "grade": ("Grade", "M1"),
    "location": ("Location", "Lahore"),
    "payroll": ("Payroll", "Monthly"),
    "employee_type": ("Employee type", "Permanent"),
>>>>>>> origin/main
    "stage": ("Current onboarding stage", "Pre-Onboarding"),
    "status": ("Onboarding status", "Pre Onboarding"),
    "joining_date": ("Date of joining", "01 Jul 2026"),
    "company": ("Company / tenant name", "Demo Company"),
<<<<<<< HEAD
    "company_name": ("Company / tenant name", "Demo Company"),
    "current_date": ("Current date", "15 Oct 2026"),
=======
>>>>>>> origin/main
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
<<<<<<< HEAD
    """Built-in (editable) + custom templates as a flat list for the admin UI."""
=======
>>>>>>> origin/main
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
<<<<<<< HEAD
    """Create/update a custom template. Placeholders are detected from content."""
=======
>>>>>>> origin/main
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
<<<<<<< HEAD
    """Build the tag→value map for a specific employee (for sendable templates)."""
    from .services.template_context import tenant_template_context
    context = tenant_template_context(emp.tenant if emp.tenant_id else None)
    context.update({
=======
    return {
>>>>>>> origin/main
        "full_name": emp.full_name or "",
        "email": emp.email or "",
        "employee_id": emp.employee_id or "",
        "position_title": emp.position_title or "",
        "department": emp.department.name if emp.department_id else "",
<<<<<<< HEAD
=======
        "grade": emp.grade or "",
        "location": emp.location_code or "",
        "payroll": emp.payroll or "",
        "employee_type": emp.employee_type or "",
>>>>>>> origin/main
        "stage": (emp.status or "").replace("_", " ").title(),
        "status": (emp.status or "").replace("_", " ").title(),
        "joining_date": emp.date_of_joining.strftime("%d %b %Y") if emp.date_of_joining else "",
        "company": emp.tenant.name if emp.tenant_id else "",
        "link": link, "message": message, "title": title,
<<<<<<< HEAD
    })
    return context


def render_email(key, context):
    """Render (subject, body) for a template key, applying {placeholder} values.

    Resolves an admin override, then a custom template, then the built-in default.
    """
=======
    }


def render_email(key, context):
>>>>>>> origin/main
    overrides = get_email_templates().get(key, {})
    custom = get_custom_templates().get(key, {})
    default = EMAIL_TEMPLATE_DEFAULTS.get(key, {})
    subject = (overrides.get("subject") or custom.get("subject") or default.get("subject") or "").strip()
    body = overrides.get("body") or custom.get("body") or default.get("body") or ""
    for k, v in (context or {}).items():
<<<<<<< HEAD
        value = str(v)
        for ph in ("{{" + k + "}}", "{{ " + k + " }}", "{" + k + "}"):
            subject = subject.replace(ph, value)
            body = body.replace(ph, value)
=======
        ph = "{" + k + "}"
        subject = subject.replace(ph, str(v))
        body = body.replace(ph, str(v))
>>>>>>> origin/main
    return subject, body


def send_email(to, subject, body, html=None):
<<<<<<< HEAD
    """Synchronous send. Returns (ok, error_message). Never raises."""
    if not smtp_configured():
        return False, "SMTP is not configured."
    recipients = [to] if isinstance(to, str) else list(to)
    try:
        msg = EmailMultiAlternatives(subject, body, from_address(), recipients,
                                     connection=_connection())
        if html:
            msg.attach_alternative(html, "text/html")
        msg.send()
        return True, None
    except Exception as exc:  # noqa: BLE001 - surface any SMTP error to caller
        return False, str(exc)


def send_email_async(to, subject, body, html=None, on_sent=None):
    """Send without blocking the request. `on_sent(ok, err)` runs after delivery.

    Returns the Thread (or None when sent synchronously, e.g. in tests).
    """
=======
    """Send synchronously through SMTP."""
    recipients = [to] if isinstance(to, str) else list(to)
    if not recipients:
        return False, "No email recipients were supplied."

    if not smtp_configured():
        return False, "Email is not configured. Please configure SMTP."

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
>>>>>>> origin/main
    def _run():
        try:
            ok, err = send_email(to, subject, body, html)
            if on_sent:
                try:
                    on_sent(ok, err)
                except Exception:
                    pass
        finally:
<<<<<<< HEAD
            # Release per-thread DB connections opened by AppSetting queries.
            connections.close_all()

    if getattr(settings, "EMAIL_ASYNC", True):
        thread = threading.Thread(target=_run, daemon=True)
=======
            connections.close_all()

    if getattr(settings, "EMAIL_ASYNC", True):
        thread = threading.Thread(target=_run, daemon=True, name="onboardhub-email")
>>>>>>> origin/main
        thread.start()
        return thread
    _run()
    return None
