"""
Reminder scheduling and dispatch service.

NOTE: Reminders are now stored in Engagement.data['reminders'] or AppSetting.
This service is deprecated but kept for reference.
"""
from datetime import timedelta
from django.utils import timezone
from ..models import User


def schedule_stage_reminders(employee: User, stage_key: str) -> list:
    """
    Schedule reminders for an employee entering a stage.

    Reminders are now stored in Engagement records instead of a separate table.
    This function is a no-op for backwards compatibility.

    Args:
        employee: User instance
        stage_key: Stage key (e.g., 'pre_onboarding')

    Returns:
        Empty list
    """
    return []
