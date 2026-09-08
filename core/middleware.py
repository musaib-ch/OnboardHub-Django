"""Idle-session timeout + last-activity tracking + audit logging."""
from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone


class LastActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            timeout_min = getattr(settings, "SESSION_TIMEOUT_MINUTES", 30)
            last = request.session.get("_last_activity_ts")
            now = timezone.now().timestamp()
            if last and (now - last) > timeout_min * 60:
                logout(request)
                if request.method == "GET":
                    from django.contrib import messages
                    messages.warning(request, "Your session has expired. Please sign in again.")
                    return redirect("login")
            else:
                request.session["_last_activity_ts"] = now
                if not user.last_activity or (
                    timezone.now() - user.last_activity
                ).total_seconds() > 60:
                    from django.contrib.auth import get_user_model
                    get_user_model().objects.filter(pk=user.pk).update(
                        last_activity=timezone.now()
                    )
        response = self.get_response(request)
        self._audit_request(request, response)
        return response

    @staticmethod
    def _audit_request(request, response):
        """Record state-changing portal actions not already explicitly audited."""
        if getattr(request, "_audit_logged", False):
            return
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return
        path = request.path or ""
        if path.startswith("/admin/settings/logs/"):
            return
        try:
            from django.urls import resolve
            from .services import log_activity
            match = resolve(path)
            action = match.url_name or path.strip("/").replace("/", "_") or "portal_action"
        except Exception:
            action = path.strip("/").replace("/", "_") or "portal_action"

        status_label = "succeeded" if response.status_code < 400 else "failed"
        log_activity(
            request=request,
            user=user,
            action=f"{request.method.lower()}_{action}"[:100],
            entity_type="portal_action",
            description=f"{request.method} {path} {status_label} (HTTP {response.status_code})",
        )
