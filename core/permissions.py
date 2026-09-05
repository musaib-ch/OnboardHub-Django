"""
Role permission matrix — ported from app/security/permission_matrix.py.

Role-level defaults live here; per-user deviations are stored on
User.permissions_override (replacing the old user_permission table).
Custom roles are stored in AppSetting JSON so the 13-table schema stays intact.
"""
import json
import re


BUILTIN_ROLE_META = {
    "super_admin": {"label": "Super Admin", "base": "staff", "scope_type": None},
    "admin": {"label": "Admin", "base": "staff", "scope_type": None},
    "hrbp": {"label": "HRBP", "base": "staff", "scope_type": "department"},
    "medical_approver": {"label": "Medical Approver", "base": "staff", "scope_type": "location"},
    "offer_sender": {"label": "Offer Sender", "base": "staff", "scope_type": None},
    "employee": {"label": "Employee", "base": "employee", "scope_type": None},
}

BASE_ROLE_PERMISSIONS = {
    "super_admin": [
        # All permissions - super admin has everything
        "view_employees", "manage_users",
        "bypass_stages", "on_behalf_documents",
        "medical_review", "approve_medical", "request_medical_resubmission", "request_medical_info", "manage_medical_requirements",
        "manage_training", "assign_training", "view_training",
        "view_programs", "manage_landing_page",
        "manage_forms", "manage_documents", "export_data",
        "manage_automation_rules", "manage_organization", "manage_appearance",
        "manage_stages", "manage_stage_templates", "customize_employee_workflow",
        "manage_onboarding_plans", "view_analytics",
        "approve_pre_onboarding", "approve_onboarding", "approve_post_onboarding",
        # Offer-related permissions
        "send_offer", "manage_offers", "revoke_offer", "export_offer", "approve_offer",
        "create_live_sessions", "manage_live_sessions",
    ],
    "admin": [
        # Admin: manage users, forms, documents, org setup, training, plans (Offers restricted to super_admin and offer_sender)
        "view_employees", "manage_users",
        "manage_forms", "manage_documents", "export_data",
        "manage_training", "assign_training", "view_training",
        "view_programs", "manage_landing_page",
        "manage_organization", "manage_appearance",
        "manage_automation_rules", "manage_onboarding_plans", "view_analytics",
        "manage_stages", "manage_stage_templates", "customize_employee_workflow",
        "approve_pre_onboarding", "approve_onboarding", "approve_post_onboarding",
        "create_live_sessions", "manage_live_sessions",
    ],
    "medical_approver": [
        # Medical approver: only medical-related permissions
        "medical_review", "approve_medical",
        "request_medical_resubmission", "request_medical_info",
        "manage_medical_requirements", "bypass_stages",
    ],
    "hrbp": [
        # HRBP: view employees, manage training, view programs, manage 30/60/90 plans
        "view_employees",
        "manage_training", "assign_training", "view_training",
        "view_programs", "manage_onboarding_plans", "view_analytics",
        "create_live_sessions", "manage_live_sessions",
    ],
    "offer_sender": [
        # Offer sender: dedicated role for offer management
        "send_offer", "manage_offers", "revoke_offer", "export_offer", "approve_offer",
        "manage_templates", "manage_email_templates", "manage_offer_fields",
    ],
    "employee": [],
}


# ── Permission catalog (grouped for the matrix UI) ──────────────────────────
# (category label, [(permission_key, human label), ...])
# ONLY includes permissions with actual code enforcement
PERMISSION_CATEGORIES = [
    ("People & Users", [
        ("view_employees", "View employees"),
        ("manage_users", "Create / edit users"),
    ]),
    ("Offer Management & Operations", [
        ("send_offer", "Send offer letters & documents"),
        ("manage_offers", "Review and manage offer letters"),
        ("revoke_offer", "Revoke pending offers"),
        ("export_offer", "Export offers to PDF / ZIP"),
        ("approve_offer", "Approve offer workflows"),
        ("manage_templates", "Manage offer letter templates"),
        ("manage_email_templates", "Manage offer email templates"),
    ]),
    ("Stages & Actions", [
        ("bypass_stages", "Bypass stages / complete on behalf"),
        ("on_behalf_documents", "Sign documents on behalf"),
        ("manage_onboarding_plans", "Create 30/60/90 day plans"),
        ("approve_pre_onboarding", "Approve pre-onboarding"),
        ("approve_onboarding", "Approve onboarding"),
        ("approve_post_onboarding", "Approve post-onboarding"),
    ]),
    ("Medical", [
        ("medical_review", "Review medical documents"),
        ("approve_medical", "Approve medical"),
        ("request_medical_resubmission", "Request medical resubmission"),
        ("request_medical_info", "Request medical info"),
        ("manage_medical_requirements", "Manage medical requirements"),
    ]),
    ("Training & Learning", [
        ("manage_training", "Manage training"),
        ("assign_training", "Assign training"),
        ("view_training", "View training"),
    ]),
    ("Programs & Content", [
        ("view_programs", "View programs"),
        ("manage_landing_page", "Manage landing page"),
    ]),
    ("Live Sessions", [
        ("create_live_sessions", "Create live sessions"),
        ("manage_live_sessions", "Manage live sessions and attendance"),
    ]),
    ("Forms & Documents", [
        ("manage_forms", "Manage forms / form builder"),
        ("manage_documents", "Manage onboarding documents"),
        ("export_data", "Export data"),
        # Offer templates and fields management
        ("manage_templates", "Manage offer templates"),
        ("manage_email_templates", "Manage offer email templates"),
        ("manage_offer_fields", "Manage offer fields"),
    ]),
    ("Configuration", [
        ("manage_automation_rules", "Automation rules"),
        ("manage_organization", "Organization setup"),
        ("manage_appearance", "Appearance / branding"),
        ("manage_stages", "Manage workflow stages"),
        ("manage_stage_templates", "Manage workflow templates"),
        ("customize_employee_workflow", "Customize employee workflow"),
        ("view_analytics", "View analytics dashboard"),
    ]),
]

ALL_PERMISSIONS = [key for _cat, perms in PERMISSION_CATEGORIES for key, _label in perms]

# Roles whose defaults are editable on the Roles & Permissions page.
EDITABLE_ROLES = ["admin", "hrbp", "medical_approver", "offer_sender", "employee"]

_ROLE_PERMS_KEY = "role_perms_overrides"  # AppSetting key holding {role: [perms]}
_CUSTOM_ROLES_KEY = "custom_roles"


def slug_role(value):
    key = re.sub(r"[^a-z0-9_]+", "_", (value or "").strip().lower())
    key = re.sub(r"_+", "_", key).strip("_")
    return key[:30]


def custom_roles():
    from .models import AppSetting
    raw = AppSetting.get(_CUSTOM_ROLES_KEY)
    try:
        data = json.loads(raw) if raw else []
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    cleaned = []
    seen = set(BUILTIN_ROLE_META)
    for item in data:
        if not isinstance(item, dict):
            continue
        key = slug_role(item.get("key"))
        if not key or key in seen:
            continue
        base = item.get("base") if item.get("base") in ("staff", "employee") else "staff"
        scope_type = item.get("scope_type") if item.get("scope_type") in ("department", "location") else None
        cleaned.append({
            "key": key,
            "label": (item.get("label") or key.replace("_", " ").title()).strip(),
            "base": base,
            "scope_type": scope_type,
            "permissions": sorted(set(item.get("permissions") or []) & set(ALL_PERMISSIONS)),
        })
        seen.add(key)
    return cleaned


def save_custom_roles(roles, user=None):
    from .models import AppSetting
    AppSetting.set(_CUSTOM_ROLES_KEY, json.dumps(roles), user=user)


def custom_role(key):
    key = slug_role(key)
    return next((r for r in custom_roles() if r["key"] == key), None)


def all_roles(include_super=True):
    roles = []
    for key, meta in BUILTIN_ROLE_META.items():
        if key == "super_admin" and not include_super:
            continue
        roles.append({"key": key, **meta, "custom": False})
    roles.extend({**r, "custom": True} for r in custom_roles())
    return roles


def editable_roles():
    return EDITABLE_ROLES + [r["key"] for r in custom_roles()]


def role_label(key):
    if key in BUILTIN_ROLE_META:
        return BUILTIN_ROLE_META[key]["label"]
    role = custom_role(key)
    return role["label"] if role else (key or "").replace("_", " ").title()


def role_base(key):
    if key in BUILTIN_ROLE_META:
        return BUILTIN_ROLE_META[key]["base"]
    role = custom_role(key)
    return role["base"] if role else "employee"


def role_scope_type(key):
    if key in BUILTIN_ROLE_META:
        return BUILTIN_ROLE_META[key]["scope_type"]
    role = custom_role(key)
    return role["scope_type"] if role else None


def is_staff_role(key):
    return role_base(key) == "staff"


def is_employee_role(key):
    return role_base(key) == "employee"


def _role_overrides():
    from .models import AppSetting
    raw = AppSetting.get(_ROLE_PERMS_KEY)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def resolve_role_permissions(role_name):
    """Editable override (from AppSetting) if present, else the code default."""
    role = custom_role(role_name)
    if role:
        return set(role.get("permissions") or [])
    overrides = _role_overrides()
    if role_name in overrides:
        return set(overrides[role_name])
    return set(BASE_ROLE_PERMISSIONS.get(role_name, []))


def set_role_permissions(role_name, perms, user=None):
    """Persist a role's permission set (AppSetting JSON — no extra table)."""
    safe_perms = sorted(set(perms) & set(ALL_PERMISSIONS))
    roles = custom_roles()
    for role in roles:
        if role["key"] == role_name:
            role["permissions"] = safe_perms
            save_custom_roles(roles, user=user)
            return
    from .models import AppSetting
    overrides = _role_overrides()
    overrides[role_name] = safe_perms
    AppSetting.set(_ROLE_PERMS_KEY, json.dumps(overrides), user=user)


def role_permission_map():
    """{role: sorted([perms])} for all known roles (super_admin = everything)."""
    m = {"super_admin": sorted(set(ALL_PERMISSIONS))}
    for r in editable_roles():
        m[r] = sorted(resolve_role_permissions(r))
    return m


def upsert_custom_role(key, label, base, scope_type, perms, user=None):
    key = slug_role(key or label)
    if not key or key in BUILTIN_ROLE_META:
        return None
    base = base if base in ("staff", "employee") else "staff"
    scope_type = scope_type if scope_type in ("department", "location") else None
    record = {
        "key": key,
        "label": (label or key.replace("_", " ").title()).strip(),
        "base": base,
        "scope_type": scope_type,
        "permissions": sorted(set(perms or []) & set(ALL_PERMISSIONS)),
    }
    roles = [r for r in custom_roles() if r["key"] != key]
    roles.append(record)
    roles.sort(key=lambda r: r["label"].lower())
    save_custom_roles(roles, user=user)
    return record


def delete_custom_role(key, user=None):
    key = slug_role(key)
    roles = custom_roles()
    remaining = [r for r in roles if r["key"] != key]
    if len(remaining) == len(roles):
        return False
    save_custom_roles(remaining, user=user)
    return True
