"""
Sequential onboarding pipeline.

Stages run strictly in order; each stage is locked until the previous one is
**approved** by a reviewer:

    medical  ->  pre_onboarding  ->  onboarding  ->  post_onboarding  ->  completed

Each stage has the same lifecycle:
    active -> submitted -> (approved: advance) | changes_requested | info_requested | rejected

Disabled stages (via stage_settings) are skipped entirely.

NOTE: As of Phase 1, stages can now be configured via the database (StageDefinition model).
The hardcoded constants below remain for backward compatibility but delegate to pipeline_v2
where possible. New code should prefer pipeline_v2 functions.
"""
from .services import stage_flags
from . import pipeline_v2  # New configurable stage system

STAGE_ORDER = ["offer", "medical", "pre_onboarding", "onboarding", "post_onboarding"]

STAGE_LABELS = {
    "offer": "Offer Acceptance",
    "medical": "Medical Clearance",
    "pre_onboarding": "Pre-Onboarding",
    "onboarding": "Onboarding",
    "post_onboarding": "Post-Onboarding",
}

# The status an employee gets when they first enter a stage (editable).
ENTRY_STATUS = {
    "medical": "medical_upload",
    "pre_onboarding": "pre_onboarding",
    "offer": "offer",
    "onboarding": "onboarding",
    "post_onboarding": "post_onboarding",
}

# The status set when an employee submits a stage for review.
SUBMIT_STATUS = {
    "medical": "medical_under_review",
    "pre_onboarding": "pre_onboarding_submitted",
    "offer": "offer_submitted",
    "onboarding": "onboarding_submitted",
    "post_onboarding": "post_onboarding_submitted",
}

SUBMITTED_STATUSES = set(SUBMIT_STATUS.values())

# status -> stage it belongs to
_STAGE_OF = {"pending": None, "completed": "__done__",
             "on_hold": None, "archived": None, "deleted": None}
for _stage in STAGE_ORDER:
    for _suffix in ("upload", "under_review", "submitted", "resubmission",
                    "info_requested", "rejected"):
        _STAGE_OF[f"{_stage}_{_suffix}"] = _stage
    _STAGE_OF[_stage] = _stage  # bare "pre_onboarding"/"onboarding"/... = active


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURABLE WORKFLOW DELEGATION (Pipeline V2)
# ─────────────────────────────────────────────────────────────────────────────

def get_employee_stage_path(user):
    """Get employee's custom stage path or fall back to global defaults.
    (Delegates to pipeline_v2)
    """
    return pipeline_v2.get_employee_stage_path(user)


def current_stage(user):
    """Get current stage for employee (from configurable system).
    Replaces the hardcoded version below.
    (Delegates to pipeline_v2)
    """
    return pipeline_v2.current_stage_for_user(user)


def next_stage(user):
    """Get next stage for employee in their custom path.
    (Delegates to pipeline_v2)
    """
    return pipeline_v2.next_stage_for_user(user)


def advance_employee_to_next_stage(user, modified_by=None):
    """Advance employee to next stage in their custom path.
    (Delegates to pipeline_v2)
    """
    return pipeline_v2.advance_employee_to_next_stage(user, modified_by=modified_by)


# ─────────────────────────────────────────────────────────────────────────────


def stage_flag_key(stage):
    return {
        "medical": "medical_enabled",
        "pre_onboarding": "pre_onboarding_enabled",
        "offer": "offer_enabled",
        "onboarding": "onboarding_enabled",
        "post_onboarding": "post_onboarding_enabled",
    }[stage]


def enabled_stages():
    flags = stage_flags()
    return [s for s in STAGE_ORDER if flags.get(stage_flag_key(s), True)]


def stage_of_status(status):
    return _STAGE_OF.get(status)


def progress_index(user):
    """Index (in the employee''s path) of the stage the employee is currently in.

    Equals len(path) when the employee has completed everything.
    """
    stages = get_employee_stage_path(user) or enabled_stages()
    if not stages:
        return 0
    if user.status == "completed":
        return len(stages)
    current = current_stage(user)
    if current in stages:
        return stages.index(current)
    st = stage_of_status(user.status)
    if st in stages:
        return stages.index(st)
    if user.status == "pending":
        return 0
    return 0


def stage_state(user, stage):
    """One of: locked, active, submitted, changes_requested, info_requested,
    rejected, completed, disabled."""
    stages = get_employee_stage_path(user) or enabled_stages()
    if stage not in stages:
        return "disabled"
    if stage == "offer":
        from .models_offers import Offer
        offer = Offer.objects.filter(candidate_user=user).order_by("-created_at").first()
        if offer and offer.status == "accepted":
            return "completed"
        elif offer and offer.status in ("revoked", "rejected", "expired"):
            return "rejected"
        return "active"
    if stage == "medical":
        if "offer" in stages:
            offer_state = stage_state(user, "offer")
            if offer_state != "completed":
                return "locked"
        return pipeline_v2._medical_stage_state(user)
    idx = stages.index(stage)
    pidx = progress_index(user)
    if user.status == "completed":
        return "completed"
    if idx < pidx:
        return "completed"
    if idx > pidx:
        return "locked"
    s = user.status
    if s in SUBMITTED_STATUSES:
        return "submitted"
    if s.endswith("_rejected"):
        return "rejected"
    if s.endswith("_info_requested"):
        return "info_requested"
    if s.endswith("_resubmission"):
        return "changes_requested"
    return "active"


EDITABLE_STATES = {"active", "changes_requested", "info_requested"}


def is_editable(user, stage):
    return stage_state(user, stage) in EDITABLE_STATES


def is_accessible(user, stage):
    """Can the employee open this stage page at all? (current or already done)"""
    return stage_state(user, stage) in (
        "active", "changes_requested", "info_requested", "submitted",
        "rejected", "completed",
    )


def current_stage_hardcoded(user):
    """OLD: Get current stage using hardcoded pipeline (kept for backward compat).
    NEW code should use current_stage() which uses the configurable system.
    """
    stages = get_employee_stage_path(user) or enabled_stages()
    pidx = progress_index(user)
    return stages[pidx] if pidx < len(stages) else None


def remaining_stages(user):
    """Stages from the employee's current point through the end (inclusive)."""
    stages = get_employee_stage_path(user) or enabled_stages()
    pidx = progress_index(user)
    return stages[pidx:] if pidx < len(stages) else []


def entry_status_for_user(user):
    """Status to assign a freshly-started (pending) employee."""
    stages = pipeline_v2.get_employee_stage_path(user) or enabled_stages()
    return ENTRY_STATUS[stages[0]] if stages else "completed"


def next_status_after(stage):
    """Where approval of `stage` sends the employee."""
    stages = STAGE_ORDER
    if stage not in stages:
        return "completed"
    idx = stages.index(stage)
    if idx + 1 < len(stages):
        return ENTRY_STATUS[stages[idx + 1]]
    return "completed"


def review_actions_for(status):
    """Admin review actions available for a given *submitted* status.

    Returns {action: (new_status, employee-facing verb)} or {} if not reviewable.
    """
    stage = stage_of_status(status)
    if status not in SUBMITTED_STATUSES or stage not in STAGE_ORDER:
        return {}
    return {
        "approve": (None, "approved"),  # resolved to next_status_after at apply time
        "request_changes": (f"{stage}_resubmission", "sent back for changes"),
        "request_info": (f"{stage}_info_requested", "asked for more information"),
        "reject": (f"{stage}_rejected", "rejected"),
    }

