"""Injects `site_settings`, `stage_settings`, notif count and helpers into every template.

Ported from the Flask `inject_site_settings` context processor so base.html
themes identically.
"""
from .models import AppSetting, Notification
from . import services
from . import pipeline
from .permissions import ALL_PERMISSIONS, is_employee_role, is_staff_role, role_label


def _hex_to_rgb(hex_color, fallback="13,43,79"):
    h = (hex_color or "").lstrip("#")
    if not h:
        return fallback
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"
    except (ValueError, IndexError):
        return fallback


def _normalize_nav_color(value, fallback):
    raw = (value or "").strip().lower()
    if raw == "white":
        return "#ffffff"
    if raw == "black":
        return "#111111"
    if raw.startswith("#") and len(raw) in (4, 7):
        return raw
    return fallback


def site_settings(request):
    keys = [
        "site_title", "primary_color", "accent_color", "site_logo",
        "sidebar_bg", "sidebar_hover", "sidebar_active",
        "nav_text_color", "nav_active_text_color", "page_bg_color",
        "enable_email_notifications", "enable_in_app_notifications",
        "notification_sound_enabled", "notification_sound_tone", "notification_sound_volume",
        "font_family", "radius_scale", "density", "button_style", "card_style",
    ]
    rows = {r.key: (r.value or "") for r in AppSetting.objects.filter(key__in=keys)}
    settings = {k: rows.get(k, "") for k in keys}

    settings.setdefault("site_title", "")
    if not settings.get("primary_color"):
        settings["primary_color"] = "#1d2b4f"
    if not settings.get("accent_color"):
        settings["accent_color"] = "#324b8a"
    if not settings.get("sidebar_bg"):
        settings["sidebar_bg"] = "#1d2b4f"
    if not settings.get("sidebar_hover"):
        settings["sidebar_hover"] = "#2a3a66"
    if not settings.get("sidebar_active"):
        settings["sidebar_active"] = "#324b8a"
    if not settings.get("page_bg_color"):
        settings["page_bg_color"] = "#f8fafc"
    settings["primary_rgb"] = _hex_to_rgb(settings["primary_color"])
    settings["accent_rgb"] = _hex_to_rgb(settings["accent_color"])
    settings["nav_text_color"] = _normalize_nav_color(settings.get("nav_text_color"), "#ffffff")
    settings["nav_active_text_color"] = _normalize_nav_color(
        settings.get("nav_active_text_color"), "#ffffff"
    )

    # ── UI/UX knobs (typography, shape, density) ────────────────────────────
    settings["font_family"] = settings.get("font_family") or "Inter"
    settings["radius_scale"] = settings.get("radius_scale") or "rounded"
    settings["density"] = settings.get("density") or "comfortable"
    settings["button_style"] = settings.get("button_style") or "rounded"
    settings["card_style"] = settings.get("card_style") or "glass"
    radius_map = {
        "sharp": ("6px", "8px", "10px", "12px"),
        "rounded": ("8px", "12px", "16px", "24px"),
        "pill": ("12px", "18px", "24px", "32px"),
    }
    (settings["rad_sm"], settings["rad_md"],
     settings["rad_lg"], settings["rad_xl"]) = radius_map.get(
        settings["radius_scale"], radius_map["rounded"])
    settings["body_theme_class"] = (
        f"theme-density-{settings['density']} "
        f"theme-btn-{settings['button_style']} "
        f"theme-card-{settings['card_style']}"
    )

    unread = 0
    can_export = False
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        unread = Notification.objects.filter(user=user, is_read=False).count()
        can_export = user.has_perm_key("export_data")
        # Keep navigation and endpoint authorization on the same catalog.  This is
        # deliberately derived from ALL_PERMISSIONS so a newly granted permission
        # appears immediately in every portal without a second, stale allow-list.
        nav_perms = {p: user.has_perm_key(p) for p in ALL_PERMISSIONS}
        # Super admin always sees all features (even if not in permission list)
        if user.role == "super_admin":
            nav_perms.update({p: True for p in nav_perms.keys()})
            nav_perms["manage_zoom"] = True
            nav_perms["manage_sessions"] = True
        employee_role = is_employee_role(user.role)
        staff_role = is_staff_role(user.role)
        current_role_label = role_label(user.role)
        employee_stage_path = pipeline.get_employee_stage_path(user) if employee_role else []
        unlocked_stages = {}
        if employee_role:
            for s in employee_stage_path:
                unlocked_stages[s] = pipeline.stage_state(user, s) != 'locked'
    else:
        employee_role = False
        staff_role = False
        current_role_label = ""
        nav_perms = {}
        employee_stage_path = []
        unlocked_stages = {}

    return {
        "site_settings": settings,
        "stage_settings": services.stage_flags(),
        "unread_notif_count": unread,
        "onboarding_progress_percent": services.onboarding_progress_percent,
        "can_export": can_export,
        "nav_perms": nav_perms,
        "is_employee_role": employee_role,
        "is_staff_role": staff_role,
        "current_role_label": current_role_label,
        "employee_stage_path": employee_stage_path,
        "unlocked_stages": unlocked_stages,
        "role": getattr(user, "role", "") if user is not None and user.is_authenticated else "",
        # Employee assignment visibility flags — only computed for employees
        "has_learning_paths": _has_learning_paths(user) if employee_role else False,
        "has_quizzes": _has_quizzes(user) if employee_role else False,
        "has_success_plan": _has_success_plan(user) if employee_role else False,
        "has_buddy": _has_buddy(user) if employee_role else False,
    }


def _has_learning_paths(user):
    """True if this employee has any active learning path enrollment."""
    from .models import Engagement
    return Engagement.objects.filter(
        user=user, kind="enrollment", content__kind="learning_path",
    ).exclude(status="completed").exists()


def _has_quizzes(user):
    """True if the employee has any quiz assigned (standalone quiz forms)."""
    from .models import Form
    all_quizzes = Form.objects.filter(
        form_kind="quiz", is_active=True,
    )
    for q in all_quizzes:
        schema = q.schema or {}
        roles = schema.get("quiz_meta", {}).get("assigned_roles") or schema.get("settings", {}).get("assigned_roles") or []
        if user.role in roles or user.role == "super_admin":
            return True
    return False


def _has_success_plan(user):
    """True if the employee has any onboarding success plan."""
    from .models import Engagement
    return Engagement.objects.filter(
        user=user, kind="onboarding_plan",
    ).exists()


def _has_buddy(user):
    """True if this user has an assigned buddy or is acting as a buddy/mentor to someone."""
    from .models import Engagement
    has_paired_buddy = Engagement.objects.filter(kind="mentorship", user=user, status="active").exists()
    is_mentor_to_someone = Engagement.objects.filter(kind="mentorship", counterparty=user, status="active").exists()
    return has_paired_buddy or is_mentor_to_someone
