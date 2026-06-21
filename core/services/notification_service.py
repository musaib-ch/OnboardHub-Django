"""
Notification preferences and filtering service.

Determines which notifications a user should receive based on their preferences.
"""
from typing import Dict, Optional

from ..models import User

# Default notification preferences - what emails users can opt into
DEFAULT_PREFERENCES = {
    'session_invitations': True,
    'session_reminders': True,
    'session_approvals': True,
    'quiz_results': True,
    'course_enrollments': True,
    'course_completions': True,
    'stage_updates': True,
    'document_requests': True,
    'medical_approvals': True,
}


def get_preferences(user: User) -> Dict[str, bool]:
    """Get a user's notification preferences with defaults."""
    prefs = user.notification_preferences or {}
    # Merge with defaults
    result = DEFAULT_PREFERENCES.copy()
    result.update(prefs)
    return result


def set_preference(user: User, preference_key: str, enabled: bool) -> None:
    """Set a single notification preference."""
    if not user.notification_preferences:
        user.notification_preferences = {}
    user.notification_preferences[preference_key] = enabled
    user.save(update_fields=['notification_preferences'])


def set_all_preferences(user: User, preferences: Dict[str, bool]) -> None:
    """Set multiple notification preferences at once."""
    user.notification_preferences = preferences
    user.save(update_fields=['notification_preferences'])


def should_send_email(user: User, event_type: str) -> bool:
    """
    Determine if we should send an email to this user.

    Args:
        user: The recipient
        event_type: Type of notification (e.g., 'session_invitations', 'quiz_results')

    Returns:
        True if email should be sent
    """
    # Check global email notification setting
    if not user.enable_email_notifications:
        return False

    # Check specific preference
    prefs = get_preferences(user)
    return prefs.get(event_type, True)


def bulk_notify(user_ids: list, event_type: str) -> tuple:
    """
    Filter users who should receive a notification.

    Returns:
        (user_list_to_notify, user_list_skipped) - tuple of filtered lists
    """
    users = User.objects.filter(id__in=user_ids)
    to_notify = []
    skipped = []

    for user in users:
        if should_send_email(user, event_type):
            to_notify.append(user)
        else:
            skipped.append(user)

    return to_notify, skipped
