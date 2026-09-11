"""Admin Gmail API connection flow for the main portal email transport."""
import secrets

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from ..decorators import roles_required
from ..models import AppSetting
from .. import gmail_service


@roles_required("super_admin")
@require_http_methods(["GET", "POST"])
def gmail_settings(request):
    if request.method == "POST":
        action = request.POST.get("action") or "connect"
        if action == "disconnect":
            AppSetting.set("gmail_refresh_token", "", user=request.user)
            AppSetting.set("gmail_account_email", "", user=request.user)
            messages.success(request, "Gmail account disconnected. SMTP remains available as fallback.")
            return redirect("admin_gmail_settings")

        client_id = (request.POST.get("gmail_client_id") or "").strip()
        client_secret = (request.POST.get("gmail_client_secret") or "").strip()
        sender_name = (request.POST.get("gmail_sender_name") or "OnboardHub").strip()
        if not client_id or not client_secret:
            messages.error(request, "Enter the Google OAuth Client ID and Client Secret first.")
            return redirect("admin_gmail_settings")

        AppSetting.set("gmail_client_id", client_id, user=request.user)
        AppSetting.set("gmail_client_secret", client_secret, user=request.user)
        AppSetting.set("gmail_sender_name", sender_name or "OnboardHub", user=request.user)

        state = secrets.token_urlsafe(32)
        request.session["gmail_oauth_state"] = state
        request.session["gmail_oauth_next"] = reverse("admin_gmail_settings")
        request.session.modified = True

        redirect_uri = request.build_absolute_uri(reverse("admin_gmail_callback"))
        try:
            return redirect(gmail_service.authorization_url(redirect_uri, state))
        except Exception as exc:
            messages.error(request, str(exc))
            return redirect("admin_gmail_settings")

    return render(request, "admin/gmail_settings.html", {
        "client_id": gmail_service.client_id(),
        "has_client_secret": bool(gmail_service.client_secret()),
        "sender_name": gmail_service.sender_name(),
        "account_email": gmail_service.account_email(),
        "connected": gmail_service.configured(),
        "redirect_uri": request.build_absolute_uri(reverse("admin_gmail_callback")),
    })


@roles_required("super_admin")
@require_http_methods(["GET"])
def gmail_callback(request):
    expected_state = request.session.pop("gmail_oauth_state", None)
    next_url = request.session.pop("gmail_oauth_next", reverse("admin_gmail_settings"))

    if not expected_state or request.GET.get("state") != expected_state:
        messages.error(request, "Gmail authorization could not be verified. Please try Connect Gmail again.")
        return redirect(next_url)

    if request.GET.get("error"):
        detail = request.GET.get("error_description") or request.GET.get("error")
        messages.error(request, f"Gmail authorization was cancelled or denied: {detail}")
        return redirect(next_url)

    code = request.GET.get("code")
    if not code:
        messages.error(request, "Google did not return an authorization code.")
        return redirect(next_url)

    redirect_uri = request.build_absolute_uri(reverse("admin_gmail_callback"))
    try:
        token = gmail_service.exchange_code(code, redirect_uri)
        AppSetting.set("gmail_refresh_token", token, user=request.user)
        email = gmail_service.fetch_account_email()
        AppSetting.set("gmail_account_email", email, user=request.user)
        messages.success(request, f"Gmail connected successfully as {email}. Main portal email will now use Gmail API over HTTPS.")
    except Exception as exc:
        messages.error(request, f"Gmail connection failed: {exc}")
    return redirect(next_url)
