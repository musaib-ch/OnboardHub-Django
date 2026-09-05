"""
Stage management service for handling employee stage transitions and due dates.
"""
from datetime import timedelta
from django.utils import timezone
from ..models import User, AppSetting
import json


def advance_employee_to_stage(employee: User, new_status: str) -> None:
    """
    Move employee to a new stage and update due dates.

    Called when employee submits/completes a stage and moves to the next one.

    Args:
        employee: User instance
        new_status: New status string (e.g., 'pre_onboarding')
    """
    from .. import pipeline

    # Update status
    employee.status = new_status

    # Set when they entered this stage
    employee.stage_entered_at = timezone.now()

    # Calculate due date based on AppSetting stage config
    try:
        current_stage = pipeline.stage_of_status(new_status)
        stages_json = AppSetting.get('stages', '{}')
        stages_dict = json.loads(stages_json) if isinstance(stages_json, str) else stages_json
        stage_config = stages_dict.get(current_stage, {})
        days = stage_config.get('default_due_date_days', 7)
        employee.stage_due_date = employee.stage_entered_at + timedelta(days=days)
    except (ValueError, KeyError):
        employee.stage_due_date = None

    # Clear override unless explicitly set
    if not employee.stage_due_date_override:
        employee.stage_due_date_override = None

    employee.save(update_fields=[
        'status', 'stage_entered_at', 'stage_due_date', 'stage_due_date_override'
    ])


def set_stage_due_date_override(employee: User, new_due_date) -> None:
    """
    Allow HR to override the due date for an employee's current stage.

    Args:
        employee: User instance
        new_due_date: New due date (datetime or None to clear override)
    """
    employee.stage_due_date_override = new_due_date
    employee.save(update_fields=['stage_due_date_override'])


def get_stage_progress(employee: User) -> dict:
    """
    Get detailed progress information for an employee's current stage.

    Returns:
        {
            'status': 'pending' | 'in_progress' | 'overdue' | 'completed',
            'days_remaining': int or None,
            'due_date': datetime or None,
            'entered_at': datetime or None,
        }
    """
    return {
        'status': employee.stage_status(),
        'days_remaining': employee.days_remaining_in_stage(),
        'due_date': employee.get_effective_due_date(),
        'entered_at': employee.stage_entered_at,
    }
