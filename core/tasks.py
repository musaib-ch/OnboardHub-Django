"""
Celery background tasks for emails and scheduled notifications.
"""
from celery import shared_task

from .services.scheduled_reminders import (
    send_session_reminders,
    send_stage_deadline_reminders,
    send_overdue_document_reminders,
)


@shared_task
def send_session_reminders_24h():
    """Send session reminders 24 hours before start time."""
    result = send_session_reminders(days_before=1)
    return {
        'task': 'send_session_reminders_24h',
        'sent': result.get('sent', 0),
        'skipped': result.get('skipped', 0),
        'errors': result.get('errors', 0),
    }


@shared_task
def send_session_reminders_7d():
    """Send session reminders 7 days before start time."""
    result = send_session_reminders(days_before=7)
    return {
        'task': 'send_session_reminders_7d',
        'sent': result.get('sent', 0),
        'skipped': result.get('skipped', 0),
        'errors': result.get('errors', 0),
    }


@shared_task
def send_stage_deadline_reminders():
    """Send reminders about upcoming stage deadline (3 days)."""
    result = send_stage_deadline_reminders()
    return {
        'task': 'send_stage_deadline_reminders',
        'sent': result.get('sent', 0),
        'skipped': result.get('skipped', 0),
        'errors': result.get('errors', 0),
    }


@shared_task
def send_document_reminders():
    """Send reminders about overdue documents."""
    result = send_overdue_document_reminders()
    return {
        'task': 'send_document_reminders',
        'sent': result.get('sent', 0),
        'skipped': result.get('skipped', 0),
        'errors': result.get('errors', 0),
    }


@shared_task
def send_email_async(to_email, template_key, context, from_email=None):
    """Send an email asynchronously."""
    from .services.email_service import EmailService

    return EmailService.send_email(
        to_email=to_email,
        template_key=template_key,
        context=context,
        from_email=from_email,
        log_event=True,
    )
