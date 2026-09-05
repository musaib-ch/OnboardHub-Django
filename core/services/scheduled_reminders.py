"""
Scheduled email reminders for upcoming sessions and events.

Runs periodically to send reminder emails.
"""
from datetime import datetime, timedelta
from typing import List

from django.utils import timezone

from ..models import Content, Engagement, User
from .email_triggers import send_session_reminder
from .notification_service import should_send_email


def send_session_reminders(days_before: int = 1) -> dict:
    """
    Send reminder emails for sessions starting in N days.

    Args:
        days_before: Number of days before session to send reminder (default: 1 = 24 hours)

    Returns:
        {'sent': count, 'skipped': count, 'errors': count}
    """
    now = timezone.now()
    target_start = now + timedelta(days=days_before)
    target_end = now + timedelta(days=days_before + 1)

    # Find sessions scheduled to start in the target window
    sessions = Content.objects.filter(
        kind='live_session',
        meta__scheduled_date__gte=target_start.isoformat(),
        meta__scheduled_date__lt=target_end.isoformat(),
    )

    stats = {'sent': 0, 'skipped': 0, 'errors': 0}

    for session in sessions:
        try:
            # Get attendees
            registrations = Engagement.objects.filter(
                kind='session',
                content=session,
                data__status='registered'
            )

            for reg in registrations:
                user = reg.user
                if should_send_email(user, 'session_reminders'):
                    time_until = f'in {days_before} day' if days_before == 1 else f'in {days_before} days'
                    send_session_reminder(session, time_until)
                    stats['sent'] += 1
                else:
                    stats['skipped'] += 1

        except Exception as e:
            stats['errors'] += 1
            import logging
            logging.error(f'Error sending session reminder for session {session.id}: {str(e)}')

    return stats


def send_stage_deadline_reminders() -> dict:
    """
    Send reminders to employees about upcoming stage deadlines.

    Returns:
        {'sent': count, 'skipped': count, 'errors': count}
    """
    now = timezone.now()
    in_3_days = now + timedelta(days=3)

    stats = {'sent': 0, 'skipped': 0, 'errors': 0}

    # Find employees with stage due dates in next 3 days
    employees = User.objects.filter(
        stage_due_date__gte=now,
        stage_due_date__lte=in_3_days,
        role='employee',
        status__in=['pre_onboarding', 'onboarding', 'post_onboarding'],
    )

    for employee in employees:
        if should_send_email(employee, 'stage_updates'):
            try:
                from .email_service import EmailService
                days_until = (employee.stage_due_date - now).days

                context = {
                    'employee_name': employee.full_name,
                    'stage_name': employee.status.replace('_', ' ').title(),
                    'due_date': employee.stage_due_date.strftime('%B %d, %Y'),
                    'days_remaining': days_until,
                    'portal_link': 'https://app.onboardhub.com/employee/home/',
                }

                EmailService.send_email(
                    to_email=employee.email,
                    template_key='stage_deadline_reminder',
                    context=context,
                    user=employee
                )
                stats['sent'] += 1
            except Exception as e:
                stats['errors'] += 1
                import logging
                logging.error(f'Error sending stage reminder to {employee.email}: {str(e)}')
        else:
            stats['skipped'] += 1

    return stats


def send_overdue_document_reminders() -> dict:
    """
    Send reminders to employees about overdue documents/forms.

    Returns:
        {'sent': count, 'skipped': count, 'errors': count}
    """
    now = timezone.now()
    stats = {'sent': 0, 'skipped': 0, 'errors': 0}

    # Find overdue form submissions
    overdue_forms = Engagement.objects.filter(
        kind='form',
        data__status='pending',
        data__due_date__lt=now.isoformat(),
    ).select_related('user', 'content')

    for form_eng in overdue_forms:
        employee = form_eng.user
        form = form_eng.content

        if should_send_email(employee, 'document_requests'):
            try:
                from .email_service import EmailService
                context = {
                    'employee_name': employee.full_name,
                    'form_title': form.title,
                    'portal_link': 'https://app.onboardhub.com/employee/home/',
                }

                EmailService.send_email(
                    to_email=employee.email,
                    template_key='document_reminder',
                    context=context,
                    user=employee
                )
                stats['sent'] += 1
            except Exception as e:
                stats['errors'] += 1
                import logging
                logging.error(f'Error sending document reminder to {employee.email}: {str(e)}')
        else:
            stats['skipped'] += 1

    return stats


def run_all_scheduled_reminders() -> dict:
    """
    Run all scheduled reminder jobs.

    Returns:
        Aggregated stats from all reminder jobs
    """
    results = {
        'session_reminders_24h': send_session_reminders(days_before=1),
        'session_reminders_7d': send_session_reminders(days_before=7),
        'stage_deadline_reminders': send_stage_deadline_reminders(),
        'document_reminders': send_overdue_document_reminders(),
    }

    # Aggregate totals
    total_sent = sum(r['sent'] for r in results.values())
    total_skipped = sum(r['skipped'] for r in results.values())
    total_errors = sum(r['errors'] for r in results.values())

    return {
        'total_sent': total_sent,
        'total_skipped': total_skipped,
        'total_errors': total_errors,
        'details': results,
    }
