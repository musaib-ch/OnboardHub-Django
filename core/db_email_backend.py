"""Django email backend backed by OnboardHub AppSetting SMTP configuration."""

import http.client
import json
import re
import socket
import smtplib
import urllib.parse

from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend

from .models import AppSetting


_DOH_RESOLVERS = (
    ("1.1.1.1", "cloudflare-dns.com"),
    ("8.8.8.8", "dns.google"),
)


class _DirectHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection to a resolver IP while preserving TLS SNI/Host."""

    def __init__(self, resolver_ip, server_name, timeout):
        super().__init__(server_name, 443, timeout=timeout)
        self.resolver_ip = resolver_ip
        self.server_name = server_name

    def connect(self):
        sock = socket.create_connection((self.resolver_ip, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.server_name)


def _resolve_via_doh(host, timeout=8):
    """Resolve an A record without depending on the application's DNS."""
    path = "/dns-query?" + urllib.parse.urlencode({"name": host, "type": "A"})
    last_error = None

    for resolver_ip, server_name in _DOH_RESOLVERS:
        conn = None
        try:
            conn = _DirectHTTPSConnection(resolver_ip, server_name, timeout)
            conn.request(
                "GET", path,
                headers={
                    "Accept": "application/dns-json",
                    "Host": server_name,
                    "User-Agent": "OnboardHub/1.0",
                },
            )
            response = conn.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            addresses = [
                answer.get("data")
                for answer in payload.get("Answer", [])
                if answer.get("type") == 1 and answer.get("data")
            ]
            if addresses:
                return addresses
            last_error = RuntimeError(f"No A record returned for '{host}'")
        except Exception as exc:
            last_error = exc
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    raise socket.gaierror(f"DNS could not resolve SMTP host '{host}'") from last_error


class ResilientSMTP(smtplib.SMTP):
    """SMTP client that prefers IPv4 A records and bypasses broken IPv6 routing."""

    def _get_socket(self, host, port, timeout):
        try:
            addresses = _resolve_via_doh(host, timeout=min(timeout or 15, 8))
        except Exception:
            addresses = None

        if addresses:
            last_error = None
            for address in addresses:
                try:
                    return socket.create_connection((address, port), timeout, self.source_address)
                except OSError as exc:
                    last_error = exc
            if last_error:
                raise last_error

        return super()._get_socket(host, port, timeout)


class ResilientSMTPSSL(smtplib.SMTP_SSL):
    """SSL SMTP client with the same IPv4/DNS resilience as ResilientSMTP."""

    def _get_socket(self, host, port, timeout):
        try:
            addresses = _resolve_via_doh(host, timeout=min(timeout or 15, 8))
        except Exception:
            addresses = None

        if addresses:
            last_error = None
            for address in addresses:
                try:
                    return socket.create_connection((address, port), timeout, self.source_address)
                except OSError as exc:
                    last_error = exc
            if last_error:
                raise last_error

        return super()._get_socket(host, port, timeout)


class AppSettingEmailBackend(SMTPEmailBackend):
    """SMTP backend whose connection settings come from AppSetting."""

    @property
    def connection_class(self):
        return ResilientSMTPSSL if self.use_ssl else ResilientSMTP

    @staticmethod
    def _audit_email(email_message, ok, error=None):
        try:
            from .services import log_activity
            recipients = email_message.recipients()
            detail = (
                f"SMTP {'accepted' if ok else 'failed'} email; "
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

    def _send(self, email_message):
        if not email_message.recipients():
            self._audit_email(email_message, False, "No recipients")
            return False
        from_email = self.prep_address(email_message.from_email)
        recipients = [self.prep_address(addr) for addr in email_message.recipients()]
        message = email_message.message()
        try:
            refused = self.connection.sendmail(from_email, recipients, message.as_bytes(linesep="\r\n"))
        except Exception as exc:
            self._audit_email(email_message, False, f"{type(exc).__name__}: {exc}")
            if not self.fail_silently:
                raise
            return False
        if refused:
            error = smtplib.SMTPRecipientsRefused(refused)
            self._audit_email(email_message, False, str(error))
            raise error
        self._audit_email(email_message, True)
        return True

    @staticmethod
    def _clean_host(value):
        value = (value or "").replace("\ufeff", "").strip().strip('"\'')
        value = re.sub(r"^smtps?://", "", value, flags=re.IGNORECASE)
        value = value.split("/", 1)[0].strip()
        if value.count(":") == 1:
            value = value.rsplit(":", 1)[0].strip()
        return value.rstrip(".").strip()

    @staticmethod
    def _clean_value(value):
        return (value or "").replace("\ufeff", "").strip().strip('"\'')

    def __init__(self, fail_silently=False, **kwargs):
        host = self._clean_host(AppSetting.get("smtp_host") or "")
        username = self._clean_value(AppSetting.get("smtp_user") or "")
        password = self._clean_value(AppSetting.get("smtp_password") or "")

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
