"""
Configurable workflow system — database-driven stage pipeline (v2).

Replaces hardcoded STAGE_ORDER with StageDefinition model.
Supports per-employee custom stage paths via EmployeeStagePath.
"""
from functools import lru_cache
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta

from .models import StageDefinition, StageTemplate, EmployeeStagePath, User, AppSetting


# ─────────────────────────────────────────────────────────────────────────────
# STAGE DEFINITIONS & RETRIEVAL
# ─────────────────────────────────────────────────────────────────────────────

def get_stage_definitions(enabled_only=True):
    """Fetch all stage definitions, optionally filtered to enabled only.
    Cached for performance.
    """
    cache_key = 'stage_definitions_enabled' if enabled_only else 'stage_definitions_all'
    stages = cache.get(cache_key)
    if stages is None:
        qs = StageDefinition.objects.order_by('order')
        if enabled_only:
            qs = qs.filter(is_enabled=True)
        stages = list(qs.values())
        cache.set(cache_key, stages, 3600)  # Cache for 1 hour
    return stages


def get_stage_definition(stage_key):
    """Get a single stage definition by key."""
    try:
        return StageDefinition.objects.get(stage_key=stage_key)
    except StageDefinition.DoesNotExist:
        return None


def clear_stage_cache():
    """Clear cached stage definitions (call after creating/modifying stages)."""
    cache.delete('stage_definitions_enabled')
    cache.delete('stage_definitions_all')


# ─────────────────────────────────────────────────────────────────────────────
# STAGE PATH MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

def get_employee_stage_path(user):
    """Get this employee's custom stage path, or fall back to global defaults.

    Returns: List of stage_keys in order. Example: ["offer_acceptance", "medical", "pre_onboarding", ...]
    """
    if user.stage_path:
        return user.stage_path.stages
    return get_global_default_stages()


def get_global_default_stages():
    """Get the default stage sequence for new employees.

    Returns only ENABLED stages - disabled stages are filtered out.

    Reads from:
    1. AppSetting 'default_stage_template' (template name)
    2. Falls back to first StageTemplate with is_global=True
    3. Falls back to hardcoded list if no template exists

    All disabled stages are filtered out from the result.
    """
    # Get all enabled stage keys
    enabled_stages = set(StageDefinition.objects.filter(is_enabled=True).values_list("stage_key", flat=True))

    template_key = AppSetting.get("default_stage_template", "")

    if template_key:
        try:
            template = StageTemplate.objects.get(name=template_key, is_active=True)
            # Filter to only enabled stages
            return [s for s in template.stages if s in enabled_stages]
        except StageTemplate.DoesNotExist:
            pass

    # Fallback: use first global template
    template = StageTemplate.objects.filter(is_global=True, is_active=True).first()
    if template:
        # Filter to only enabled stages
        return [s for s in template.stages if s in enabled_stages]

    # Final fallback: hardcoded standard flow (for backward compatibility)
    # Also filter to only enabled stages
    fallback = ["medical", "pre_onboarding", "onboarding", "post_onboarding"]
    return [s for s in fallback if s in enabled_stages]


def create_employee_stage_path(user, stages, change_reason=""):
    """Create or update an employee's custom stage path.

    Args:
        user: User instance (must be employee role)
        stages: List of stage_keys to assign
        change_reason: Reason for the change (for audit trail)

    Returns: EmployeeStagePath instance
    """
    path, created = EmployeeStagePath.objects.update_or_create(
        employee=user,
        defaults={
            'stages': stages,
            'change_reason': change_reason,
            'modified_by': None,  # Could be set from request.user
        }
    )
    return path


# ─────────────────────────────────────────────────────────────────────────────
# STAGE STATE & PROGRESSION
# ─────────────────────────────────────────────────────────────────────────────

# Mapping from status to stage_key (backward compatible with hardcoded system)
STATUS_TO_STAGE = {
    # Medical
    'medical_upload': 'medical',
    'medical_under_review': 'medical',
    'medical_info_requested': 'medical',
    'medical_resubmission': 'medical',
    'medical_rejected': 'medical',
    # Pre-onboarding
    'pre_onboarding': 'pre_onboarding',
    'pre_onboarding_submitted': 'pre_onboarding',
    'pre_onboarding_resubmission': 'pre_onboarding',
    'pre_onboarding_info_requested': 'pre_onboarding',
    'pre_onboarding_rejected': 'pre_onboarding',
    # Onboarding
    'onboarding': 'onboarding',
    'onboarding_submitted': 'onboarding',
    'onboarding_resubmission': 'onboarding',
    'onboarding_info_requested': 'onboarding',
    'onboarding_rejected': 'onboarding',
    # Post-onboarding
    'post_onboarding': 'post_onboarding',
    'post_onboarding_submitted': 'post_onboarding',
    'post_onboarding_resubmission': 'post_onboarding',
    'post_onboarding_info_requested': 'post_onboarding',
    'post_onboarding_rejected': 'post_onboarding',
    # Optional/special stages
    'offer_acceptance': 'offer_acceptance',
    'offer_rejected': 'offer_acceptance',
    'orientation': 'orientation',
    'training': 'training',
    'onboarding_30_60_90': 'onboarding_30_60_90',
}

# Entry statuses when employee enters a stage
ENTRY_STATUS = {
    'medical': 'medical_upload',
    'offer_acceptance': 'offer_acceptance',
    'pre_onboarding': 'pre_onboarding',
    'onboarding': 'onboarding',
    'post_onboarding': 'post_onboarding',
    'orientation': 'orientation',
    'training': 'training',
    'onboarding_30_60_90': 'onboarding_30_60_90',
}

# Stage labels for UI
STAGE_LABELS = {
    'medical': 'Medical Clearance',
    'offer_acceptance': 'Offer Acceptance',
    'pre_onboarding': 'Pre-Onboarding',
    'onboarding': 'Onboarding',
    'post_onboarding': 'Post-Onboarding',
    'orientation': 'Orientation',
    'training': 'Training',
    'onboarding_30_60_90': '30/60/90 Day Plan',
}


def current_stage_for_user(user):
    """Get the current stage key for an employee based on their status.

    Returns: stage_key string or None if no active stage
    """
    if not user.status or user.status in ('pending', 'completed', 'deleted', 'on_hold'):
        return None

    # Look up stage from status
    stage_key = STATUS_TO_STAGE.get(user.status)
    if not stage_key:
        return None

    # Verify it's in the employee's stage path (optional check)
    path = get_employee_stage_path(user)
    if stage_key not in path:
        return None

    return stage_key


def next_stage_for_user(user):
    """Get the next stage in this employee's path.

    Returns: stage_key string or None if at end of path
    """
    path = get_employee_stage_path(user)
    current = current_stage_for_user(user)

    if not current:
        # If no current stage, return first stage
        return path[0] if path else None

    try:
        idx = path.index(current)
        return path[idx + 1] if idx + 1 < len(path) else None
    except ValueError:
        return None


def previous_stage_for_user(user):
    """Get the previous stage in this employee's path (for history).

    Returns: stage_key string or None if at beginning of path
    """
    path = get_employee_stage_path(user)
    current = current_stage_for_user(user)

    if not current:
        return None

    try:
        idx = path.index(current)
        return path[idx - 1] if idx > 0 else None
    except ValueError:
        return None


def advance_employee_to_next_stage(user, modified_by=None):
    """Advance employee to the next stage in their path.

    Args:
        user: User instance to advance
        modified_by: User instance who approved the advancement (for logging)

    Returns: True if advanced, False if already at end
    """
    next_stage = next_stage_for_user(user)
    if not next_stage:
        return False

    stage_def = get_stage_definition(next_stage)
    if not stage_def:
        return False

    # Set entry status and due date
    user.status = ENTRY_STATUS.get(next_stage, f"{next_stage}_submitted")
    user.stage_entered_at = timezone.now()
    user.stage_due_date = timezone.now() + timedelta(days=stage_def.default_due_date_days)
    user.stage_due_date_override = None  # Clear any override
    user.save(update_fields=['status', 'stage_entered_at', 'stage_due_date', 'stage_due_date_override'])

    return True


def complete_all_stages(user):
    """Mark employee as completed all stages."""
    user.status = 'completed'
    user.save(update_fields=['status'])


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

def get_all_templates(active_only=True):
    """Get all stage templates."""
    qs = StageTemplate.objects.filter(is_global=True)
    if active_only:
        qs = qs.filter(is_active=True)
    return list(qs.values())


def get_template(name):
    """Get a template by name."""
    try:
        return StageTemplate.objects.get(name=name)
    except StageTemplate.DoesNotExist:
        return None


def set_default_template(name):
    """Set which template is used by default for new employees."""
    AppSetting.set('default_stage_template', name)
    clear_stage_cache()
