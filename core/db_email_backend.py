"""Django email backend backed by OnboardHub AppSetting SMTP configuration."""

import http.client
import json
import re
import socket
import smtplib
import ssl

from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend

from .models import AppSetting


# Public resolver IPs. Connecting to the IP directly avoids depending on the
# application's broken DNS resolver just to resolve the resolver hostname.
_DOH_RESOLVERS = (
    ("1.1.1.1", "cloudflare-dns.com"),
    ("8.8.8.8", "dns.google"),
)


def _resolve_via_doh(host, timeout=8):
    """Resolve an A record without relying on the local DNS resolver."""
    path = "/dns-query?name=" + host + "&type=A"
    last_error = None

    for resolver_ip, server_name in _DOH_RESOLVERS:
        try:
            raw_sock = socket.create_connection((resolver_ip, 443), timeout=timeout)
            context = ssl.create_default_context()
            tls_sock = context.wrap_socket(raw_sock, server_hostname=server_name)
            conn = http.client.HTTPSConnection(server_name, 443, timeout=timeout)
            # Replace the connection's normal DNS-created socket with our
            # already-connected TLS socket. The Host header preserves the
            # resolver hostname required by the DoH service.
            conn.sock = tls_sock
            conn._HTTPConnection__state = http.client._CS_IDLE
            conn.request("GET", path, headers={
                "Accept": "application/dns-json",
                "Host": server_name,
                "User-Agent": "OnboardHub/1.0",
            })
            response = conn.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            conn.close()

            addresses = [
                answer.get("data")
                for answer in payload.get("Answer", [])
                if answer.get("type") == 1 and answer.get("data")
            ]
            if addresses:
                return addresses
            last_error = RuntimeError(
                f"DNS resolver returned no A record for '{host}'"
            )
        except Exception as exc:  # noqa: BLE001 - try the second resolver
            last_error = exc

    if last_error:
        raise socket.gaierror(f"DNS could not resolve SMTP host '{host}'") from last_error
    raise socket.gaierror(f"DNS could not resolve SMTP host '{host}'")


class ResilientSMTP(smtplib.SMTP):
    """SMTP client with a direct-IP DNS-over-HTTPS fallback."""

    def _get_socket(self, host, port, timeout):
        try:
            return super()._get_socket(host, port, timeout)
        except socket.gaierror:
            addresses = _resolve_via_doh(host, timeout=min(timeout or 15, 8))
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
        value = (value or "").replace("\ufeff", "").strip().strip('"\'')
        value = re.sub(r"^smtps?://", "", value, flags=re.IGNORECASE)
        value = value.split("/", 1)[0].strip()
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
