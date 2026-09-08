"""Django email backend that reads SMTP configuration from AppSetting.

This keeps all application email (including code that calls django.core.mail.send_mail)
consistent with the SMTP settings configured in the OnboardHub admin panel.
"""

from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend

from .models import AppSetting


class AppSettingEmailBackend(SMTPEmailBackend):
    """SMTP backend whose connection settings come from the database."""

    def __init__(self, fail_silently=False, **kwargs):
        # AppSetting.get() is intentionally evaluated when an email connection is
        # created, not during Django startup, so migrations and management commands
        # can still run before the AppSetting table exists.
        host = (AppSetting.get("smtp_host") or "").strip()
        username = (AppSetting.get("smtp_user") or "").strip()
        password = AppSetting.get("smtp_password") or ""

        try:
            port = int(AppSetting.get("smtp_port") or 587)
        except (TypeError, ValueError):
            port = 587

        use_tls = (AppSetting.get("smtp_use_tls", "true") or "true").strip().lower() == "true"
        use_ssl = (AppSetting.get("smtp_use_ssl", "false") or "false").strip().lower() == "true"

        # Django's SMTP backend rejects using TLS and SSL together. Prefer the
        # explicitly selected SSL mode if both were accidentally enabled.
        if use_ssl:
            use_tls = False

        super().__init__(
            fail_silently=fail_silently,
            host=host,
            port=port,
            username=username,
            password=password,
            use_tls=use_tls,
            use_ssl=use_ssl,
            timeout=15,
            **kwargs,
        )
