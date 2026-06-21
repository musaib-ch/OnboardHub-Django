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
