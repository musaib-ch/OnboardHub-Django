"""Injects `site_settings`, `stage_settings`, notif count and helpers into every template.

Ported from the Flask `inject_site_settings` context processor so base.html
themes identically.
"""
from .models import AppSetting, Notification
from . import services
from .permissions import is_employee_role, is_staff_role, role_label


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
        nav_perms = {p: user.has_perm_key(p) for p in (
            "view_employees", "manage_users", "manage_forms", "manage_documents",
            "manage_medical_requirements", "medical_review", "view_knowledge",
            "manage_training", "manage_orientation", "view_presentation",
            "manage_appearance", "manage_organization", "manage_landing_page",
            "manage_automation_rules", "manage_email_templates",
        )}
        # Super admin always sees all features (even if not in permission list)
        if user.role == "super_admin":
            nav_perms.update({p: True for p in nav_perms.keys()})
            nav_perms["manage_zoom"] = True
            nav_perms["manage_sessions"] = True
        employee_role = is_employee_role(user.role)
        staff_role = is_staff_role(user.role)
        current_role_label = role_label(user.role)
    else:
        employee_role = False
        staff_role = False
        current_role_label = ""
        nav_perms = {}

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
    }
