"""Idle-session timeout + last-activity tracking."""
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
                # Only redirect GET requests; let POST fail naturally (CSRF will catch it)
                if request.method == "GET":
                    from django.contrib import messages
                    messages.warning(request, "Your session has expired. Please sign in again.")
                    return redirect("login")
            else:
                request.session["_last_activity_ts"] = now
                # Lightweight last_activity stamp (throttled to once per minute)
                if not user.last_activity or (
                    timezone.now() - user.last_activity
                ).total_seconds() > 60:
                    from django.contrib.auth import get_user_model
                    get_user_model().objects.filter(pk=user.pk).update(
                        last_activity=timezone.now()
                    )
        return self.get_response(request)
