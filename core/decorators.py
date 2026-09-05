"""Role / permission decorators (mirror Flask's login_required + permission checks)."""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def login_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        # Force password change before anything else (matches Flask behaviour).
        if request.user.must_change_password and request.resolver_match.url_name not in (
            "change_password", "logout",
        ):
            return redirect("change_password")
        return view(request, *args, **kwargs)
    return wrapper


def roles_required(*roles):
    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            # Super admin always has access
            if request.user.role == 'super_admin':
                return view(request, *args, **kwargs)
            if request.user.role not in roles:
                messages.error(request, "You do not have access to that page.")
                return redirect("index")
            return view(request, *args, **kwargs)
        return wrapper
    return deco


def permission_required(perm):
    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            # Super admin always has permission
            if request.user.role == 'super_admin':
                return view(request, *args, **kwargs)
            if not request.user.has_perm_key(perm):
                messages.error(request, "You do not have permission for that action.")
                return redirect("index")
            return view(request, *args, **kwargs)
        return wrapper
    return deco


def staff_required(view):
    """Any non-employee role (admin console access)."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        from .permissions import is_staff_role
        if not is_staff_role(request.user.role):
            messages.error(request, "You do not have access to that page.")
            return redirect("index")
        return view(request, *args, **kwargs)
    return wrapper
