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
    return value or "pending"


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
