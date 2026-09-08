"""Django email backend backed by OnboardHub AppSetting SMTP configuration.

The admin SMTP page is the single source of truth. The backend also tolerates
restricted hosting environments where normal DNS lookup can fail by resolving
SMTP hostnames through DNS-over-HTTPS and then connecting to the resolved IP
while retaining the original hostname for TLS/SNI and certificate validation.
"""

import json
import re
import socket
import smtplib
import ssl
import urllib.parse
import urllib.request

from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend

from .models import AppSetting


class ResilientSMTP(smtplib.SMTP):
    """SMTP client with a DNS-over-HTTPS fallback."""

    def _get_socket(self, host, port, timeout):
        try:
            return super()._get_socket(host, port, timeout)
        except socket.gaierror:
            # Normal DNS failed. Resolve the same hostname through Google's
            # public DNS-over-HTTPS endpoint, then connect directly to an IPv4
            # address. STARTTLS still uses self._host (the original hostname),
            # so Gmail certificate/SNI validation remains correct.
            query = urllib.parse.urlencode({"name": host, "type": "A"})
            url = "https://dns.google/resolve?" + query
            request = urllib.request.Request(
                url,
                headers={"Accept": "application/dns-json", "User-Agent": "OnboardHub/1.0"},
            )
            with urllib.request.urlopen(request, timeout=min(timeout or 15, 8)) as response:
                payload = json.loads(response.read().decode("utf-8"))

            addresses = [
                answer.get("data")
                for answer in payload.get("Answer", [])
                if answer.get("type") == 1 and answer.get("data")
            ]
            if not addresses:
                raise socket.gaierror(f"DNS could not resolve SMTP host '{host}'")

            last_error = None
            for address in addresses:
                try:
                    if self.debuglevel > 0:
                        self._print_debug("connect: DNS-over-HTTPS resolved", (host, address, port))
                    return socket.create_connection((address, port), timeout, self.source_address)
                except OSError as exc:
                    last_error = exc

            if last_error:
                raise last_error
            raise socket.gaierror(f"Unable to connect to SMTP host '{host}'")


class AppSettingEmailBackend(SMTPEmailBackend):
    """SMTP backend whose connection settings come from AppSetting."""

    connection_class = ResilientSMTP

    @staticmethod
    def _clean_host(value):
        """Normalize common SMTP host input mistakes without changing valid hosts."""
        value = (value or "").replace("\ufeff", "").strip().strip('"\'')
        value = re.sub(r"^smtps?://", "", value, flags=re.IGNORECASE)
        value = value.split("/", 1)[0].strip()
        # Accept a pasted hostname:port value as well as separate fields.
        if value.count(":") == 1:
            value = value.rsplit(":", 1)[0].strip()
        return value.rstrip(".").strip()

    def __init__(self, fail_silently=False, **kwargs):
        host = self._clean_host(AppSetting.get("smtp_host") or "")
        username = (AppSetting.get("smtp_user") or "").replace("\ufeff", "").strip()
        password = AppSetting.get("smtp_password") or ""

        try:
            port = int(AppSetting.get("smtp_port") or 587)
        except (TypeError, ValueError):
            port = 587

        use_tls = (AppSetting.get("smtp_use_tls", "true") or "true").strip().lower() == "true"
        use_ssl = (AppSetting.get("smtp_use_ssl", "false") or "false").strip().lower() == "true"
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
