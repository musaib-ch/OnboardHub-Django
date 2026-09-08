"""Email service with SMTP and HTTPS transactional-provider support.

SMTP settings live in AppSetting keys: smtp_host, smtp_port, smtp_user,
smtp_password, smtp_use_tls, smtp_use_ssl, smtp_from_name, smtp_from_email.

For hosting environments where outbound SMTP is blocked, set:
  EMAIL_PROVIDER=brevo
  BREVO_API_KEY=<secret>
  BREVO_SENDER_EMAIL=<verified sender>
  BREVO_SENDER_NAME=<sender name>

The Brevo API uses normal HTTPS (443), avoiding direct SMTP network restrictions.
"""
import os
import threading

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import connections

from .models import AppSetting

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def brevo_configured():
    return bool(os.getenv("BREVO_API_KEY", "").strip() and
                (os.getenv("BREVO_SENDER_EMAIL", "").strip() or
                 AppSetting.get("smtp_from_email") or
                 AppSetting.get("smtp_user")))


def email_provider():
    configured = (os.getenv("EMAIL_PROVIDER", "") or "").strip().lower()
    if configured:
        return configured
    if brevo_configured():
        return "brevo"
    return "smtp"


def smtp_configured():
    return bool((AppSetting.get("smtp_host") or "").strip()) or brevo_configured()


def _flag(key, default="false"):
    return (AppSetting.get(key, default) or default).strip().lower() == "true"


def from_address():
    name = (os.getenv("BREVO_SENDER_NAME", "") or AppSetting.get("smtp_from_name") or "OnboardHub").strip()
    email = (os.getenv("BREVO_SENDER_EMAIL", "") or AppSetting.get("smtp_from_email")
             or AppSetting.get("smtp_user") or "noreply@onboardhub.local").strip()
    return f"{name} <{email}>"


def _connection():
    """Return the resilient AppSetting-backed SMTP backend."""
    return get_connection(
        backend="core.db_email_backend.AppSettingEmailBackend",
        fail_silently=False,
    )


def _audit_email(to, subject, ok, error=None, provider=None, message_id=None):
    """Record a durable email audit entry without affecting mail delivery."""
    try:
        from .services import log_activity
        recipients = [to] if isinstance(to, str) else list(to)
        detail = (
            f"Email {'accepted' if ok else 'failed'} via {provider or email_provider()}; "
            f"to={', '.join(recipients)}; subject={subject!r}"
        )
        if message_id:
            detail += f"; message_id={message_id}"
        if error:
            detail += f"; error={error}"
        log_activity(action="email_sent" if ok else "email_failed",
                     entity_type="email", description=detail)
    except Exception:
        pass


def _send_brevo(to, subject, body, html=None):
    """Send transactional email over HTTPS using Brevo's REST API."""
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    sender_email = (os.getenv("BREVO_SENDER_EMAIL", "").strip() or
                    AppSetting.get("smtp_from_email") or AppSetting.get("smtp_user") or "").strip()
    sender_name = (os.getenv("BREVO_SENDER_NAME", "").strip() or
                   AppSetting.get("smtp_from_name") or "OnboardHub").strip()
    if not api_key:
        return False, "BREVO_API_KEY is not configured."
    if not sender_email:
        return False, "BREVO_SENDER_EMAIL is not configured."

    recipients = [to] if isinstance(to, str) else list(to)
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": address} for address in recipients],
        "subject": subject,
        "textContent": body,
    }
    if html:
        payload["htmlContent"] = html

    try:
        response = requests.post(
            BREVO_API_URL,
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        if 200 <= response.status_code < 300:
            try:
                data = response.json()
            except ValueError:
                data = {}
            message_id = data.get("messageId") or data.get("messageIds", [None])[0]
            _audit_email(to, subject, True, provider="brevo", message_id=message_id)
            return True, None

        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:1000]
        error = f"Brevo HTTP {response.status_code}: {detail}"
        _audit_email(to, subject, False, error=error, provider="brevo")
        return False, error
    except requests.RequestException as exc:
        error = f"{type(exc).__name__}: {exc}"
        _audit_email(to, subject, False, error=error, provider="brevo")
        return False, error
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        _audit_email(to, subject, False, error=error, provider="brevo")
        return False, error


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
    """Synchronous send. Returns (ok, error_message). Never raises."""
    provider = email_provider()
    if not smtp_configured():
        return False, "No email provider is configured."

    recipients = [to] if isinstance(to, str) else list(to)
    if provider in {"brevo", "https", "api"}:
        return _send_brevo(recipients, subject, body, html)

    try:
        msg = EmailMultiAlternatives(subject, body, from_address(), recipients,
                                     connection=_connection())
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
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread
    _run()
    return None
