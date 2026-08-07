from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from ..models import User
from ..services import log_activity
from ..decorators import login_required
from ..permissions import is_employee_role, is_staff_role


def post_login_destination(user):
    if is_employee_role(user.role):
        return "portal" if not user.has_seen_welcome else "employee_home"
    if is_staff_role(user.role) and not user.has_seen_welcome:
        return "portal"
    return "admin_dashboard"


PRE_JOIN_STATUSES = {
    "pre_onboarding", "pre_onboarding_resubmission", "pre_onboarding_info_requested",
    "pre_onboarding_submitted", "onboarding", "post_onboarding", "completed",
}


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("index")

    email = ""
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=email, password=password)
        if user is not None:
            if user.status == "deleted":
                messages.error(request, "This account is no longer available.")
                return redirect("login")
            if user.status == "on_hold":
                messages.error(request, "Your account is on hold. Please contact HR.")
                return redirect("login")
            login(request, user)
            request.session.set_expiry(0)
            log_activity(request, user=user, action="login", entity_type="user",
                         entity_id=user.id, description=f"User {user.email} logged in")
            if user.must_change_password:
                return redirect("change_password")
            if (is_employee_role(user.role) and not user.date_of_joining
                    and user.status in PRE_JOIN_STATUSES):
                return redirect("employee_set_joining_date")
            return redirect("index")
        messages.error(request, "Invalid email or password. Please try again.")

    return render(request, "login.html", {"email": email})


@login_required
def logout_view(request):
    log_activity(request, user=request.user, action="logout", entity_type="user",
                 entity_id=request.user.id, description=f"User {request.user.email} logged out")
    logout(request)
    return redirect("login")


@require_http_methods(["GET", "POST"])
def forgot_password(request):
    if request.user.is_authenticated:
        return redirect("index")
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        user = User.objects.filter(email__iexact=email).exclude(status="deleted").first()
        if user:
            token = user.generate_password_reset_token()
            user.save(update_fields=["password_reset_token", "password_reset_expires_at"])
            reset_url = request.build_absolute_uri(f"/reset-password/{token}/")
            log_activity(request, user=user, action="password_reset_requested",
                         entity_type="user", entity_id=user.id,
                         description=f"Password reset requested for {user.email}")
            from ..services.email_service import EmailService, _big_login_cta
            from django.core.mail import get_connection
            from ..models import AppSetting
            smtp_host = AppSetting.get("smtp_host") or ""
            if smtp_host.strip():
                EmailService.send_email(
                    to_email=user.email,
                    template_key="credentials_reset",
                    context={
                        "full_name": user.full_name or user.email,
                        "reset_link": reset_url,
                        "big_login_cta": _big_login_cta(reset_url)
                    }
                )
                messages.success(request, "A password reset link has been sent to your email.")
            else:
                # No SMTP configured (dev) — surface the link so the flow stays usable.
                messages.warning(request, f"Email is not configured. Reset link: {reset_url}")
        else:
            messages.error(request, "Account not found for this email address.")
        return redirect("login")
    return render(request, "auth/forgot_password.html")


@require_http_methods(["GET", "POST"])
def reset_password(request, token):
    token = (token or "").strip()
    user = User.objects.filter(password_reset_token=token).first()
    if not user or not user.verify_password_reset_token(token):
        messages.error(request, "This password reset link is invalid or has expired.")
        return redirect("forgot_password")

    if request.method == "POST":
        password = request.POST.get("password", "")
        confirm = request.POST.get("confirm_password", "")
        err = _validate_password(password, confirm)
        if err:
            messages.error(request, err)
            return redirect(request.path)
        user.set_password(password)
        user.must_change_password = False
        user.clear_password_reset_token()
        user.save()
        messages.success(request, "Your password has been reset. Please sign in.")
        return redirect("login")
    return render(request, "auth/reset_password.html")


@login_required
@require_http_methods(["GET", "POST"])
def change_password(request):
    if request.method == "POST":
        password = request.POST.get("password", "")
        confirm = request.POST.get("confirm_password", "")
        err = _validate_password(password, confirm)
        if err:
            messages.error(request, err)
            return redirect(request.path)
        user = request.user
        user.set_password(password)
        user.must_change_password = False
        user.clear_password_reset_token()
        if is_employee_role(user.role) and not user.activated_at:
            user.activated_at = timezone.now()
        user.save()
        # set_password rotates the hash; keep the session alive.
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, user)
        messages.success(request, "Password updated successfully!")
        return redirect(post_login_destination(user))
    return render(request, "auth/change_password.html")


@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    user = request.user
    if request.method == "POST":
        user.full_name = (request.POST.get("full_name") or user.full_name).strip()
        user.phone_number = (request.POST.get("phone_number") or "").strip()
        user.enable_email_notifications = bool(request.POST.get("enable_email_notifications"))
        user.enable_in_app_notifications = bool(request.POST.get("enable_in_app_notifications"))
        avatar = request.FILES.get("avatar")
        if avatar:
            err = _save_avatar(user, avatar)
            if err:
                messages.error(request, err)
                return redirect("profile")
        user.save()
        messages.success(request, "Profile updated successfully!")
        return redirect("profile")
    return render(request, "auth/profile.html", {"profile_user": user})


def activate(request, token):
    token = (token or "").strip()
    user = User.objects.filter(onboarding_token=token).first()
    if not user:
        messages.error(request, "Invalid activation link.")
        return redirect("login")
    if user.onboarding_token_expires_at and user.onboarding_token_expires_at < timezone.now():
        messages.warning(request, "This activation link has expired. Please request a new link.")
        return redirect("login")
    login(request, user)
    user.onboarding_token = None
    user.onboarding_token_expires_at = None
    user.save(update_fields=["onboarding_token", "onboarding_token_expires_at"])
    return redirect("change_password")


@login_required
@require_http_methods(["GET", "POST"])
def notification_preferences(request):
    """Manage email notification preferences."""
    from ..services.notification_service import get_preferences, set_all_preferences, DEFAULT_PREFERENCES

    user = request.user

    if request.method == "POST":
        # Get all preference keys from form
        prefs = {}
        for key in DEFAULT_PREFERENCES.keys():
            prefs[key] = request.POST.get(f'pref_{key}') == 'on'

        # Update global email notification setting
        user.enable_email_notifications = request.POST.get('enable_email_notifications') == 'on'
        user.enable_in_app_notifications = request.POST.get('enable_in_app_notifications') == 'on'
        user.save()

        # Update granular preferences
        set_all_preferences(user, prefs)

        messages.success(request, "Notification preferences updated!")
        return redirect("notification_preferences")

    current_prefs = get_preferences(user)

    ctx = {
        'preferences': [
            {
                'key': 'session_invitations',
                'label': 'Session Invitations',
                'description': 'Get notified when invited to a live session or meeting',
                'enabled': current_prefs.get('session_invitations', True),
            },
            {
                'key': 'session_reminders',
                'label': 'Session Reminders',
                'description': 'Get reminded before upcoming sessions (24 hours & 7 days)',
                'enabled': current_prefs.get('session_reminders', True),
            },
            {
                'key': 'session_approvals',
                'label': 'Session Approvals',
                'description': 'Get notified when your session request is approved or rejected',
                'enabled': current_prefs.get('session_approvals', True),
            },
            {
                'key': 'quiz_results',
                'label': 'Quiz Results',
                'description': 'Get your quiz results and feedback after completion',
                'enabled': current_prefs.get('quiz_results', True),
            },
            {
                'key': 'course_enrollments',
                'label': 'Course Enrollments',
                'description': 'Get notified when enrolled in a new learning path',
                'enabled': current_prefs.get('course_enrollments', True),
            },
            {
                'key': 'course_completions',
                'label': 'Course Completions',
                'description': 'Get congratulations message when you complete a course',
                'enabled': current_prefs.get('course_completions', True),
            },
            {
                'key': 'stage_updates',
                'label': 'Stage Updates',
                'description': 'Get notified about onboarding stage changes and deadlines',
                'enabled': current_prefs.get('stage_updates', True),
            },
            {
                'key': 'document_requests',
                'label': 'Document Requests',
                'description': 'Get reminded about pending documents and forms',
                'enabled': current_prefs.get('document_requests', True),
            },
            {
                'key': 'medical_approvals',
                'label': 'Medical Document Updates',
                'description': 'Get notified about your medical document review status',
                'enabled': current_prefs.get('medical_approvals', True),
            },
        ],
        'enable_email_notifications': user.enable_email_notifications,
        'enable_in_app_notifications': user.enable_in_app_notifications,
    }

    return render(request, "auth/notification_preferences.html", ctx)


# ── helpers ──────────────────────────────────────────────────────────────────
def _validate_password(password, confirm):
    if not password:
        return "Password is required"
    if password != confirm:
        return "Passwords do not match"
    if len(password) < 8:
        return "Password must be at least 8 characters"
    return None


def _save_avatar(user, avatar):
    import os
    from django.conf import settings
    ext = avatar.name.rsplit(".", 1)[-1].lower() if "." in avatar.name else ""
    if ext not in {"jpg", "jpeg", "png", "webp"}:
        return "Invalid image format. Allowed: jpg, jpeg, png, webp"
    if avatar.size > 2 * 1024 * 1024:
        return "Avatar size must be less than 2MB."
    folder = os.path.join(settings.MEDIA_ROOT, "avatars")
    os.makedirs(folder, exist_ok=True)
    filename = f"user_{user.id}_{avatar.name}"
    with open(os.path.join(folder, filename), "wb") as fh:
        for chunk in avatar.chunks():
            fh.write(chunk)
    user.avatar = filename
    return None
