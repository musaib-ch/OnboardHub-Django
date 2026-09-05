"""
Configurable workflow system — database-driven stage pipeline (v2).

Replaces hardcoded STAGE_ORDER with StageDefinition model.
Supports per-employee custom stage paths via EmployeeStagePath.
"""
from functools import lru_cache
from typing import List
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta

from .models import StageDefinition, StageTemplate, EmployeeStagePath, User, AppSetting, MedicalRecord


# ─────────────────────────────────────────────────────────────────────────────
# STAGE DEFINITIONS & RETRIEVAL
# ─────────────────────────────────────────────────────────────────────────────

PORTAL_STAGE_KEYS = ["offer", "medical", "pre_onboarding", "onboarding", "post_onboarding"]


def _merge_stage_paths(base: List[str], defaults: List[str]) -> List[str]:
    """Keep a custom path in order, but reinsert any missing default stages."""
    base = [s for s in (base or []) if s]
    defaults = [s for s in (defaults or []) if s]
    result = list(base)
    for stage in defaults:
        if stage in result:
            continue
        insert_at = len(result)
        for idx, existing in enumerate(result):
            try:
                if defaults.index(existing) > defaults.index(stage):
                    insert_at = idx
                    break
            except ValueError:
                continue
        result.insert(insert_at, stage)
    deduped = []
    seen = set()
    for stage in result:
        if stage in seen:
            continue
        seen.add(stage)
        deduped.append(stage)
    return deduped


def _enabled_portal_stage_keys() -> List[str]:
    enabled = []
    for stage_key in PORTAL_STAGE_KEYS:
        stage = get_stage_definition(stage_key)
        if stage and stage.is_enabled:
            enabled.append(stage_key)
    return enabled


def _offer_stage_state(user):
    """Derive offer status from the candidate's offer records."""
    try:
        from .models_offers import Offer
        from django.db.models import Q
        offers = list(Offer.objects.filter(Q(candidate_user=user) | Q(candidate_email__iexact=user.email)))
        if not offers:
            return "completed"  # No offer created/assigned for this user
        if any(o.status in ("accepted", "signed") for o in offers):
            return "completed"
        if any(o.status == "rejected" for o in offers):
            return "rejected"
        return "active"
    except Exception:
        return "completed"


def _sync_current_stage_status(user, path: List[str]) -> None:
    """Keep the stored user.status aligned with the live workflow path."""
    if not path or not user.status or user.status in ("completed", "deleted", "on_hold"):
        return

    # Find the first stage in the path that is NOT completed
    current_incomplete = None
    for stage in path:
        if stage in ("offer", "offer_acceptance"):
            if _offer_stage_state(user) != "completed":
                current_incomplete = stage
                break
        elif stage == "medical":
            if _medical_stage_state(user) != "completed":
                current_incomplete = stage
                break
        elif stage == "pre_onboarding":
            if user.status not in ("pre_onboarding_submitted", "onboarding", "onboarding_submitted", "post_onboarding", "post_onboarding_submitted", "completed"):
                current_incomplete = stage
                break
        elif stage == "onboarding":
            if user.status not in ("onboarding_submitted", "post_onboarding", "post_onboarding_submitted", "completed"):
                current_incomplete = stage
                break
        elif stage == "post_onboarding":
            if user.status != "completed":
                current_incomplete = stage
                break

    if not current_incomplete:
        # Everything is completed!
        if user.status != "completed":
            user.status = "completed"
            user.save(update_fields=["status"])
        return

    # If the user's status is in a stage that is already completed, advance them!
    current_status_stage = STATUS_TO_STAGE.get(user.status) or (
        "offer" if user.status in ("offer", "offer_acceptance") else (
            "medical" if user.status.startswith("medical") else None
        )
    )

    if current_status_stage and current_status_stage != current_incomplete:
        try:
            old_idx = path.index(current_status_stage)
            new_idx = path.index(current_incomplete)
            if old_idx < new_idx:
                new_status = ENTRY_STATUS.get(current_incomplete, current_incomplete)
                user.status = new_status
                user.stage_entered_at = timezone.now()
                stage_def = get_stage_definition(current_incomplete)
                if stage_def:
                    user.stage_due_date = timezone.now() + timedelta(days=stage_def.default_due_date_days)
                user.stage_due_date_override = None
                user.save(update_fields=["status", "stage_entered_at", "stage_due_date", "stage_due_date_override"])
        except ValueError:
            pass

    # Also keep the specific medical status synced if they are currently on medical stage
    elif current_incomplete == "medical":
        medical_state = _medical_stage_state(user)
        desired_status = {
            "active": "medical_upload",
            "submitted": "medical_under_review",
            "info_requested": "medical_info_requested",
            "rejected": "medical_rejected",
        }.get(medical_state, "medical_upload")

        if user.status != desired_status:
            user.status = desired_status
            if not user.stage_entered_at:
                user.stage_entered_at = timezone.now()
            stage_def = get_stage_definition("medical")
            if stage_def:
                user.stage_due_date = timezone.now() + timedelta(days=stage_def.default_due_date_days)
            user.stage_due_date_override = None
            user.save(update_fields=["status", "stage_entered_at", "stage_due_date", "stage_due_date_override"])

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


def _medical_stage_state(user):
    """Derive medical status from the employee's medical records."""
    records = list(MedicalRecord.objects.filter(employee=user, is_catalog=False))
    if not records:
        return "active"

    statuses = [r.status for r in records]
    required_records = [r for r in records if r.is_required]
    required_statuses = [r.status for r in required_records] or statuses

    if any(status == "rejected" for status in statuses):
        return "rejected"
    if any(status == "info_requested" for status in statuses):
        return "info_requested"
    if any(status == "under_review" for status in statuses):
        return "submitted"
    if all(status == "approved" for status in required_statuses):
        return "completed"
    if any(record.file for record in records):
        return "active"
    return "active"


# ─────────────────────────────────────────────────────────────────────────────
# STAGE PATH MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

def get_employee_stage_path(user):
    """Get this employee's custom stage path, or fall back to global defaults.

    Returns: List of stage_keys in order. Example: ["offer_acceptance", "medical", "pre_onboarding", ...]
    """
    if user.stage_path:
        path = _merge_stage_paths(user.stage_path.stages or [], _enabled_portal_stage_keys())
    else:
        path = get_global_default_stages()
    _sync_current_stage_status(user, path)
    return path


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
            # Keep template order but reinsert any enabled portal stages that were omitted.
            return _merge_stage_paths(
                [s for s in template.stages if s in enabled_stages],
                _enabled_portal_stage_keys(),
            )
        except StageTemplate.DoesNotExist:
            pass

    # Fallback: use first global template
    template = StageTemplate.objects.filter(is_global=True, is_active=True).first()
    if template:
        # Keep template order but reinsert any enabled portal stages that were omitted.
        return _merge_stage_paths(
            [s for s in template.stages if s in enabled_stages],
            _enabled_portal_stage_keys(),
        )

    # Final fallback: hardcoded standard flow (for backward compatibility)
    # Also filter to only enabled stages
    fallback = ["medical", "pre_onboarding", "onboarding", "post_onboarding"]
    return _merge_stage_paths([s for s in fallback if s in enabled_stages], _enabled_portal_stage_keys())


def create_employee_stage_path(user, stages, change_reason="", modified_by=None):
    """Create or update an employee's custom stage path.

    Args:
        user: User instance (must be employee role)
        stages: List of stage_keys to assign
        change_reason: Reason for the change (for audit trail)

    Returns: EmployeeStagePath instance
    """
    stages = list(stages or [])
    if not stages:
        current_path = getattr(user, "stage_path", None)
        if current_path:
            current_path.delete()
        if getattr(user, "stage_path_id", None) is not None:
            user.stage_path = None
            user.save(update_fields=["stage_path"])
        return None

    path, created = EmployeeStagePath.objects.update_or_create(
        employee=user,
        defaults={
            'stages': stages,
            'change_reason': change_reason,
            'modified_by': modified_by,
        }
    )
    if getattr(user, "stage_path_id", None) != path.id:
        user.stage_path = path
        user.save(update_fields=["stage_path"])
    mapped_stage = STATUS_TO_STAGE.get(user.status)
    if user.status not in ("completed", "deleted", "on_hold") and (user.status == "pending" or mapped_stage not in stages):
        first_stage = stages[0]
        user.status = ENTRY_STATUS.get(first_stage, f"{first_stage}_submitted")
        user.stage_entered_at = timezone.now()
        stage_def = get_stage_definition(first_stage)
        if stage_def:
            user.stage_due_date = timezone.now() + timedelta(days=stage_def.default_due_date_days)
        user.stage_due_date_override = None
        user.save(update_fields=["status", "stage_entered_at", "stage_due_date", "stage_due_date_override"])
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
    if not user.status or user.status in ('completed', 'deleted', 'on_hold'):
        return None

    path = get_employee_stage_path(user)
    if not path:
        return None

    offer_key = "offer" if "offer" in path else ("offer_acceptance" if "offer_acceptance" in path else None)
    if offer_key and _offer_stage_state(user) != "completed":
        return offer_key

    if "medical" in path and _medical_stage_state(user) != "completed":
        return "medical"

    if user.status == "pending":
        return path[0]

    # Look up stage from status
    stage_key = STATUS_TO_STAGE.get(user.status)
    if not stage_key:
        return path[0]

    # Verify it's in the employee's stage path (optional check)
    if stage_key not in path:
        return path[0]

    return stage_key


def next_stage_for_user(user):
    """Get the next stage in this employee's path.

    Returns: stage_key string or None if at end of path
    """
    path = get_employee_stage_path(user)
    current = current_stage_for_user(user)

    if not current:
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

    # Trigger welcome email for the new stage
    try:
        from .services.email_service import EmailService, _small_portal_link
        from django.conf import settings
        
        template_key = f"{next_stage}_welcome"
        if next_stage == "medical":
            template_key = "medical_stage_welcome"
            
        base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
        portal_link = _small_portal_link(f"{base_url}/employee/home/")
        
        # Don't fail if the template isn't registered, EmailService handles gracefully
        EmailService.send_email(
            to_email=user.email,
            template_key=template_key,
            context={
                "employee_name": user.full_name or user.email,
                "small_portal_link_onboarding": portal_link
            },
            log_event=True
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to send welcome email for stage {next_stage}: {str(e)}")

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
