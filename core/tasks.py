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
def send_raw_email_async(to_email, subject, html_message, from_email=None):
    """Send a pre-rendered HTML email asynchronously."""
    from .services.email_service import EmailService
    return EmailService.send_raw_html(to_email=to_email, subject=subject, html_message=html_message, from_email=from_email, log_event=True)


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


@shared_task
def check_expired_offers_task():
    """Find sent or pending_approval offers past expiry_date and mark them expired."""
    from django.utils import timezone
    from .models_offers import Offer, OfferStatusHistory, OfferSendToken

    now = timezone.now()
    count = 0
    qs = Offer.objects.filter(status__in=['sent', 'pending_approval', 'draft'])
    for offer in qs:
        expiry = offer.expiry_date
        if expiry and expiry < now:
            prev_status = offer.status
            offer.status = 'expired'
            offer.save()
            OfferStatusHistory.objects.create(
                offer=offer,
                from_status=prev_status,
                to_status='expired',
                changed_by=None,
                reason='Automatically expired by background task schedule'
            )
            OfferSendToken.objects.filter(offer=offer).update(used=True)
            count += 1

    return {'task': 'check_expired_offers_task', 'expired_count': count}

