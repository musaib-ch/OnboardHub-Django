from django import template

register = template.Library()


@register.filter
def dict_get(d, key):
    """Look up d[key] for a variable key (Django can't do this natively)."""
    if d is None:
        return ""
    try:
        return d.get(key, "")
    except AttributeError:
        return ""


@register.filter
def humanize_status(value):
    """'pre_onboarding' -> 'Pre Onboarding'."""
    return (value or "").replace("_", " ").title()


@register.filter
def status_class(value):
    """Bootstrap-ish badge suffix used by base.css badge-status-* classes."""
    if not value:
        return "pending"
    val = value.lower()
    mapping = {
        "under_review": "medical_under_review",
        "uploaded": "medical_upload",
        "approved": "completed",
        "rejected": "medical_rejected",
        "info_requested": "medical_info_requested",
    }
    return mapping.get(val, val)


@register.filter
def contains(haystack, needle):
    try:
        return needle in haystack
    except TypeError:
        return False


@register.filter
def get_enabled_stages(stage_keys):
    """Filter a list of stage keys to only include enabled stages.

    Usage in template: {{ template.stages|get_enabled_stages }}
    Returns: List of enabled stage keys in original order
    """
    if not stage_keys:
        return []

    from ..models import StageDefinition

    # Get all enabled stages as a set for quick lookup
    enabled_set = set(StageDefinition.objects.filter(is_enabled=True).values_list('stage_key', flat=True))

    # Filter the original list to preserve order
    return [stage_key for stage_key in stage_keys if stage_key in enabled_set]


@register.filter
def json_encode(value):
    import json
    from django.utils.safestring import mark_safe
    return mark_safe(json.dumps(value or {}))


@register.filter
def replace(value, args):
    if not value:
        return ""
    val_str = str(value)
    arg_str = str(args)
    if ":" in arg_str:
        old, new = arg_str.split(":", 1)
        return val_str.replace(old, new)
    if arg_str == "T":
        return val_str.replace("T", " ")
    return val_str.replace(arg_str, "")


@register.filter
def endswith(value, suffix):
    if not value:
        return False
    return str(value).endswith(str(suffix))


@register.filter(is_safe=True)
def render_stage_badge(employee):
    """Renders a single clean, elegant badge for an employee's current stage and status."""
    from django.utils.safestring import mark_safe
    if not employee:
        return mark_safe('<span class="stage-badge stage-badge-default"><i class="bi bi-dash-circle"></i> Not started</span>')

    stage_label = getattr(employee, 'current_stage_label', None) or "Not started"
    stage_key = str(getattr(employee, 'current_stage', '') or '')
    state = getattr(employee, 'current_stage_state', None) or getattr(employee, 'status', '') or 'active'

    s_label_lower = stage_label.lower()
    state_lower = str(state).lower().replace(" ", "_")

    # If state is locked, show clean locked badge
    if state_lower == "locked":
        return mark_safe(f'<span class="stage-badge stage-badge-locked"><i class="bi bi-lock-fill me-1"></i>{stage_label}</span>')

    # If state is under review
    if state_lower in ["submitted", "under_review", "awaiting_review", "medical_under_review"]:
        return mark_safe(f'<span class="stage-badge stage-badge-submitted"><i class="bi bi-hourglass-split me-1"></i>{stage_label}</span>')

    # If state is info requested / resubmission
    if state_lower in ["info_requested", "resubmission", "rejected"]:
        return mark_safe(f'<span class="stage-badge stage-badge-info_requested"><i class="bi bi-exclamation-circle-fill me-1"></i>{stage_label}</span>')

    # If state is on hold
    if state_lower in ["on_hold"]:
        return mark_safe(f'<span class="stage-badge stage-badge-on_hold"><i class="bi bi-pause-circle-fill me-1"></i>On Hold</span>')

    # Default / Active state -> Render single clean stage pill with icon
    if "offer" in s_label_lower or stage_key == "offer_acceptance":
        stage_cls = "stage-badge-offer"
        icon = "bi-file-earmark-check"
    elif "medical" in s_label_lower or stage_key == "medical_clearance":
        stage_cls = "stage-badge-medical"
        icon = "bi-heart-pulse"
    elif "pre" in s_label_lower or stage_key == "pre_onboarding":
        stage_cls = "stage-badge-pre"
        icon = "bi-clipboard-check"
    elif "post" in s_label_lower or stage_key == "post_onboarding":
        stage_cls = "stage-badge-post"
        icon = "bi-mortarboard"
    elif "onboarding" in s_label_lower or stage_key == "onboarding":
        stage_cls = "stage-badge-onboarding"
        icon = "bi-rocket-takeoff"
    elif "complete" in s_label_lower or stage_key == "completed":
        stage_cls = "stage-badge-completed"
        icon = "bi-check-circle-fill"
    else:
        stage_cls = "stage-badge-default"
        icon = "bi-dash-circle"

    return mark_safe(f'<span class="stage-badge {stage_cls}"><i class="bi {icon} me-1"></i>{stage_label}</span>')

