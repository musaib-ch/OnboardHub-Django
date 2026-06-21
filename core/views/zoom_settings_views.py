"""Zoom integration settings view."""
from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from ..decorators import roles_required
from ..models import AppSetting


@roles_required("super_admin", "admin")
@require_http_methods(["GET", "POST"])
def zoom_settings(request):
    """Manage Zoom OAuth integration."""
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "save":
            # Save Zoom credentials
            client_id = request.POST.get("client_id", "").strip()
            client_secret = request.POST.get("client_secret", "").strip()
            account_id = request.POST.get("account_id", "").strip()
            host_email = request.POST.get("host_email", "").strip()

            if not all([client_id, client_secret, account_id, host_email]):
                messages.error(request, "All Zoom fields are required.")
            else:
                AppSetting.set('zoom_client_id', client_id)
                AppSetting.set('zoom_client_secret', client_secret)
                AppSetting.set('zoom_account_id', account_id)
                AppSetting.set('zoom_host_email', host_email)
                messages.success(request, "Zoom integration settings saved.")

        elif action == "test":
            # Test Zoom connection
            import requests
            client_id = AppSetting.get('zoom_client_id', '')
            client_secret = AppSetting.get('zoom_client_secret', '')
            account_id = AppSetting.get('zoom_account_id', '')

            if not all([client_id, client_secret, account_id]):
                messages.error(request, "Zoom credentials not configured.")
            else:
                try:
                    response = requests.post(
                        'https://zoom.us/oauth/token',
                        auth=(client_id, client_secret),
                        data={'grant_type': 'account_credentials', 'account_id': account_id},
                        timeout=5
                    )

                    if response.status_code == 200:
                        messages.success(request, "✓ Zoom connection successful!")
                    else:
                        error_msg = response.json().get('reason', 'Unknown error')
                        messages.error(request, f"Zoom connection failed: {error_msg}")
                except Exception as e:
                    messages.error(request, f"Zoom test error: {str(e)}")

        return redirect("zoom_settings")

    # Get current settings
    zoom_settings = {
        'client_id': AppSetting.get('zoom_client_id', ''),
        'client_secret': AppSetting.get('zoom_client_secret', ''),
        'account_id': AppSetting.get('zoom_account_id', ''),
        'host_email': AppSetting.get('zoom_host_email', ''),
    }

    zoom_enabled = bool(zoom_settings['client_id'])

    # Build absolute callback URL for Zoom OAuth
    zoom_callback_url = request.build_absolute_uri('/auth/zoom/callback/')

    return render(request, "admin/zoom_settings.html", {
        'zoom_settings': zoom_settings,
        'zoom_enabled': zoom_enabled,
        'zoom_callback_url': zoom_callback_url,
    })
