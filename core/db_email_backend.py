"""Django email backend backed by OnboardHub AppSetting SMTP configuration."""

import os
import re
import smtplib
import requests

from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend

from .models import AppSetting


class AppSettingEmailBackend(SMTPEmailBackend):
    """SMTP backend whose connection settings come from AppSetting. Supports Resend API fallback."""

    @staticmethod
    def _audit_email(email_message, ok, error=None):
        try:
            from .services import log_activity
            recipients = email_message.recipients()
            detail = (
                f"Email {'accepted' if ok else 'failed'}; "
                f"from={email_message.from_email}; "
                f"to={', '.join(recipients)}; subject={email_message.subject!r}"
            )
            if error:
                detail += f"; error={error}"
            log_activity(
                action="email_sent" if ok else "email_failed",
                entity_type="email",
                description=detail,
            )
        except Exception:
            pass

    def _send_via_resend(self, email_message, api_key):
        try:
            recipients = [addr for addr in email_message.recipients()]
            payload = {
                "from": email_message.from_email,
                "to": recipients,
                "subject": email_message.subject,
            }
            html_content = next((alt[0] for alt in getattr(email_message, "alternatives", []) if alt[1] == "text/html"), None)
            if html_content:
                payload["html"] = html_content
                # Always good to provide text fallback
                if getattr(email_message, "body", None):
                    payload["text"] = email_message.body
            else:
                payload["text"] = email_message.body or " "

            headers = {
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json"
            }
            
            resp = requests.post("https://api.resend.com/emails", json=payload, headers=headers, timeout=15)
            if resp.status_code in (200, 201):
                self._audit_email(email_message, True)
                return True
            else:
                error = f"Resend API error {resp.status_code}: {resp.text}"
                self._audit_email(email_message, False, error)
                if not self.fail_silently:
                    raise Exception(error)
                return False
        except Exception as exc:
            self._audit_email(email_message, False, str(exc))
            if not self.fail_silently:
                raise
            return False

    def _send(self, email_message):
        if not email_message.recipients():
            self._audit_email(email_message, False, "No recipients")
            return False
        
        # Check if Resend API key is configured
        resend_api_key = AppSetting.get("resend_api_key")
        if resend_api_key and resend_api_key.strip():
            return self._send_via_resend(email_message, resend_api_key)

        # Fallback to SMTP
        try:
            sent = super()._send(email_message)
            if sent:
                self._audit_email(email_message, True)
            return sent
        except Exception as exc:
            config = (
                f"host={self.host!r}, port={self.port}, "
                f"tls={self.use_tls}, ssl={self.use_ssl}"
            )
            self._audit_email(
                email_message,
                False,
                f"{type(exc).__name__}: {exc}; SMTP config: {config}",
            )
            if not self.fail_silently:
                raise
            return False

    @staticmethod
    def _clean_host(value):
        value = (value or "").replace("\ufeff", "").strip().strip('\"\'')
        value = re.sub(r"^smtps?://", "", value, flags=re.IGNORECASE)
        value = value.split("/", 1)[0].strip()
        if value.count(":") == 1:
            value = value.rsplit(":", 1)[0].strip()
        return value.rstrip(".").strip()

    @staticmethod
    def _clean_value(value):
        return (value or "").replace("\ufeff", "").strip().strip('\"\'')

    def __init__(self, fail_silently=False, **kwargs):
        # Django's backend factory may pass standard SMTP connection kwargs.
        # AppSetting is the single source of truth for this portal, so remove
        # duplicates before supplying the database-backed values below.
        for key in ("host", "port", "username", "password", "use_tls", "use_ssl", "timeout"):
            kwargs.pop(key, None)

        host = self._clean_host(AppSetting.get("smtp_host") or "")
        username = self._clean_value(AppSetting.get("smtp_user") or "")

        # Match the known-working Flask portal: Render's SMTP_PASSWORD
        # environment variable takes precedence, with the encrypted AppSetting
        # password retained as the normal database-backed fallback.
        password = self._clean_value(
            os.getenv("SMTP_PASSWORD") or AppSetting.get("smtp_password") or ""
        )

        try:
            port = int(self._clean_value(AppSetting.get("smtp_port") or "587"))
        except (TypeError, ValueError):
            port = 587

        use_tls = self._clean_value(AppSetting.get("smtp_use_tls", "true")).lower() == "true"
        use_ssl = self._clean_value(AppSetting.get("smtp_use_ssl", "false")).lower() == "true"
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
