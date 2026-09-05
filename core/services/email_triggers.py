"""
Email triggers that send emails when key events happen in the system.

Called from views when sessions, quizzes, courses, etc. are created/completed.
"""
from datetime import datetime, timedelta
from typing import Optional

from .email_service import EmailService
from ..models import User


def send_session_invitation(session_obj, attendees: list) -> int:
    """Send session invitation emails to all attendees. Returns count sent."""
    context_base = {
        'employee_name': session_obj.created_by.full_name,
        'session_title': session_obj.title,
        'scheduled_date': session_obj.scheduled_date.strftime('%B %d, %Y') if session_obj.scheduled_date else 'TBA',
        'session_time': session_obj.scheduled_date.strftime('%I:%M %p') if session_obj.scheduled_date else 'TBA',
        'duration_minutes': session_obj.duration_minutes or 60,
        'zoom_join_url': session_obj.zoom_join_url or '',
        'description': session_obj.description or '',
        'approval_deadline': (datetime.now() + timedelta(days=7)).strftime('%B %d, %Y'),
    }

    emails = []
    for attendee in attendees:
        emails.append({
            'to_email': attendee.email,
            'template_key': 'session_invitation',
            'context': {**context_base, 'employee_name': attendee.full_name},
            'user': attendee,
        })

    sent, failed = EmailService.send_batch(emails)
    return sent


def send_session_approval(session_obj, approved: bool, rejection_reason: str = '') -> bool:
    """Send session approval/rejection email. Returns True if sent."""
    template_key = 'session_approved' if approved else 'session_rejected'

    context = {
        'employee_name': session_obj.created_by.full_name,
        'session_title': session_obj.title,
        'scheduled_date': session_obj.scheduled_date.strftime('%B %d, %Y') if session_obj.scheduled_date else 'TBA',
        'duration_minutes': session_obj.duration_minutes or 60,
        'zoom_join_url': session_obj.zoom_join_url or '',
        'rejection_reason': rejection_reason,
    }

    return EmailService.send_email(
        to_email=session_obj.created_by.email,
        template_key=template_key,
        context=context,
        user=session_obj.created_by
    )


def send_session_reminder(session_obj, time_until_str: str = 'in 24 hours') -> int:
    """Send session reminder to all registered attendees."""
    # Get attendees from session (assumes session has a related attendees)
    # This will depend on your Session model structure
    try:
        attendees = session_obj.attendees.all()  # or however you access attendees
    except:
        return 0

    context_base = {
        'session_title': session_obj.title,
        'scheduled_date': session_obj.scheduled_date.strftime('%B %d, %Y') if session_obj.scheduled_date else 'TBA',
        'session_time': session_obj.scheduled_date.strftime('%I:%M %p') if session_obj.scheduled_date else 'TBA',
        'time_until': time_until_str,
        'zoom_join_url': session_obj.zoom_join_url or '',
    }

    emails = []
    for attendee in attendees:
        emails.append({
            'to_email': attendee.email,
            'template_key': 'reminder_upcoming_session',
            'context': {**context_base, 'employee_name': attendee.full_name},
            'user': attendee,
        })

    sent, failed = EmailService.send_batch(emails)
    return sent


def send_quiz_results(employee: User, quiz_title: str, score: int, passing_score: int = 80,
                     feedback: str = '') -> bool:
    """Send quiz results email. Returns True if sent."""
    context = {
        'employee_name': employee.full_name,
        'quiz_title': quiz_title,
        'score': score,
        'passing_score': passing_score,
        'status': 'Passed' if score >= passing_score else 'Failed',
        'feedback': feedback or 'Keep practicing!',
    }

    return EmailService.send_email(
        to_email=employee.email,
        template_key='quiz_results',
        context=context,
        user=employee
    )


def send_course_enrollment(employee: User, course_title: str, course_description: str = '',
                          estimated_duration: int = 20, lesson_count: int = 0,
                          course_link: str = '') -> bool:
    """Send course enrollment confirmation. Returns True if sent."""
    context = {
        'employee_name': employee.full_name,
        'course_title': course_title,
        'course_description': course_description,
        'start_date': datetime.now().strftime('%B %d, %Y'),
        'estimated_duration': estimated_duration,
        'lesson_count': lesson_count,
        'course_link': course_link,
    }

    return EmailService.send_email(
        to_email=employee.email,
        template_key='course_enrollment',
        context=context,
        user=employee
    )


def send_course_completion(employee: User, course_title: str, final_score: int = 0,
                          certificate_link: str = '') -> bool:
    """Send course completion congratulations email. Returns True if sent."""
    context = {
        'employee_name': employee.full_name,
        'course_title': course_title,
        'completion_date': datetime.now().strftime('%B %d, %Y'),
        'final_score': final_score,
        'certificate_link': certificate_link,
    }

    return EmailService.send_email(
        to_email=employee.email,
        template_key='course_completed',
        context=context,
        user=employee
    )


def send_onboarding_plan_assigned(employee: User, creator: User) -> bool:
    """Send email when 30/60/90 plan is assigned to employee. Returns True if sent."""
    context = {
        'employee_name': employee.full_name,
        'creator_name': creator.full_name,
        'plan_link': f'/employee/onboarding-plan/',
        'start_date': employee.date_of_joining.strftime('%B %d, %Y') if employee.date_of_joining else 'TBA',
    }

    return EmailService.send_email(
        to_email=employee.email,
        template_key='onboarding_plan_assigned',
        context=context,
        user=employee
    )


def send_onboarding_plan_feedback(employee: User, manager: User, phase: str) -> bool:
    """Send email when manager posts feedback on plan. Returns True if sent."""
    phase_labels = {
        'day_30': '30 Days',
        'day_60': '60 Days',
        'day_90': '90 Days',
    }

    context = {
        'employee_name': employee.full_name,
        'manager_name': manager.full_name,
        'phase': phase_labels.get(phase, phase),
        'plan_link': f'/employee/onboarding-plan/',
    }

    return EmailService.send_email(
        to_email=employee.email,
        template_key='onboarding_plan_feedback',
        context=context,
        user=employee
    )
