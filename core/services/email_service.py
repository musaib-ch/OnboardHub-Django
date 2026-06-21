"""
Email service for sending templated emails with variable substitution.

Supports email templates, logging, and bulk sending.
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.core.mail import send_mail
from django.template import Context, Template
from django.utils import timezone

from ..models import AppSetting, User
from ..services import log_activity

logger = logging.getLogger(__name__)

# Default email templates - stored in AppSetting['email_templates']
DEFAULT_TEMPLATES = {
    'session_invitation': {
        'subject': 'You\'re invited to {{session_title}}',
        'body': '''Hi {{employee_name}},

You've been invited to attend {{session_title}}.

Date: {{scheduled_date}}
Duration: {{duration_minutes}} minutes
Meeting: {{zoom_join_url}}

{{description}}

Please confirm your attendance by {{approval_deadline}}.

Best regards,
OnboardHub Team'''
    },
    'session_approved': {
        'subject': '{{session_title}} has been approved',
        'body': '''Hi {{employee_name}},

Your requested session "{{session_title}}" has been approved.

Date: {{scheduled_date}}
Duration: {{duration_minutes}} minutes
Zoom: {{zoom_join_url}}

You can now share the meeting link with attendees.

Best regards,
OnboardHub Team'''
    },
    'session_rejected': {
        'subject': '{{session_title}} was not approved',
        'body': '''Hi {{employee_name}},

Your session request "{{session_title}}" was not approved.

Reason: {{rejection_reason}}

Please contact your HRBP for more information.

Best regards,
OnboardHub Team'''
    },
    'quiz_results': {
        'subject': 'Quiz Results: {{quiz_title}}',
        'body': '''Hi {{employee_name}},

You've completed the quiz: {{quiz_title}}

Your Score: {{score}}%
Status: {{status}}
Passing Score: {{passing_score}}%

{{feedback}}

Best regards,
OnboardHub Team'''
    },
    'course_enrollment': {
        'subject': 'You\'ve been enrolled in {{course_title}}',
        'body': '''Hi {{employee_name}},

You've been enrolled in the learning path: {{course_title}}

Start Date: {{start_date}}
Duration: {{estimated_duration}} hours
Lessons: {{lesson_count}}

{{course_description}}

Start learning: {{course_link}}

Best regards,
OnboardHub Team'''
    },
    'course_completed': {
        'subject': 'Congratulations! You completed {{course_title}}',
        'body': '''Hi {{employee_name}},

Congratulations on completing {{course_title}}!

Completion Date: {{completion_date}}
Final Score: {{final_score}}%

Your certificate has been generated. You can download it from your learning dashboard.

{{certificate_link}}

Best regards,
OnboardHub Team'''
    },
    'reminder_upcoming_session': {
        'subject': 'Reminder: {{session_title}} starts soon',
        'body': '''Hi {{employee_name}},

This is a reminder that {{session_title}} starts {{time_until}}.

Date: {{scheduled_date}}
Time: {{session_time}}
Zoom: {{zoom_join_url}}

See you there!

Best regards,
OnboardHub Team'''
    },
    'onboarding_plan_assigned': {
        'subject': 'Your 30/60/90 Day Onboarding Plan',
        'body': '''Hi {{employee_name}},

Welcome to the team! {{creator_name}} has created your personalized 30/60/90 day onboarding plan.

Your plan includes specific milestones for your first 30, 60, and 90 days. This structured approach will help you succeed and get up to speed quickly.

Start Date: {{start_date}}

View your plan and track progress: {{plan_link}}

Looking forward to working with you!

Best regards,
{{creator_name}} and the team'''
    },
    'onboarding_plan_feedback': {
        'subject': '{{manager_name}} shared feedback on your {{phase}} milestone',
        'body': '''Hi {{employee_name}},

{{manager_name}} has shared feedback on your {{phase}} milestone in your onboarding plan.

Please log in to view the feedback and continue progressing through your plan.

View your plan: {{plan_link}}

Best regards,
OnboardHub Team'''
    },
    'chat_mention': {
        'subject': '{{sender_name}} mentioned you in a message',
        'body': '''Hi {{employee_name}},

{{sender_name}} mentioned you in a message:

"{{message_preview}}"

View the conversation: {{chat_link}}

Best regards,
OnboardHub Team'''
    }
}


class EmailService:
    """Service for sending templated emails with logging."""

    @staticmethod
    def get_templates() -> Dict:
        """Get all email templates from AppSetting."""
        templates_json = AppSetting.get('email_templates', '{}')
        try:
            templates = json.loads(templates_json) if isinstance(templates_json, str) else templates_json
        except (json.JSONDecodeError, TypeError):
            templates = {}

        # Merge with defaults if not found
        for key, default_template in DEFAULT_TEMPLATES.items():
            if key not in templates:
                templates[key] = default_template

        return templates

    @staticmethod
    def get_template(template_key: str) -> Optional[Dict]:
        """Get a single email template by key."""
        templates = EmailService.get_templates()
        return templates.get(template_key)

    @staticmethod
    def save_templates(templates: Dict) -> None:
        """Save email templates to AppSetting."""
        AppSetting.set('email_templates', json.dumps(templates))

    @staticmethod
    def render_template(template_key: str, context: Dict) -> Tuple[str, str]:
        """
        Render a template with given context variables.

        Returns: (subject, body)
        """
        template = EmailService.get_template(template_key)
        if not template:
            raise ValueError(f'Template "{template_key}" not found')

        subject_tpl = Template(template['subject'])
        body_tpl = Template(template['body'])

        ctx = Context(context)
        subject = subject_tpl.render(ctx)
        body = body_tpl.render(ctx)

        return subject, body

    @staticmethod
    def send_email(
        to_email: str,
        template_key: str,
        context: Dict,
        from_email: Optional[str] = None,
        log_event: bool = True,
        user: Optional[User] = None
    ) -> bool:
        """
        Send an email using a template.

        Args:
            to_email: Recipient email address
            template_key: Key of the template to use
            context: Template variables
            from_email: Sender email (uses setting if not provided)
            log_event: Whether to log the email
            user: User to associate with the email log

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Get SMTP config
            from_email = from_email or AppSetting.get('smtp_from_email', settings.DEFAULT_FROM_EMAIL)

            # Render template
            subject, body = EmailService.render_template(template_key, context)

            # Send email
            send_mail(
                subject=subject,
                message=body,
                from_email=from_email,
                recipient_list=[to_email],
                fail_silently=False,
            )

            # Log the email
            if log_event:
                EmailService.log_email(
                    to_email=to_email,
                    template_key=template_key,
                    subject=subject,
                    status='sent',
                    user=user
                )

            logger.info(f'Email sent: {template_key} to {to_email}')
            return True

        except Exception as e:
            logger.error(f'Failed to send email {template_key} to {to_email}: {str(e)}')
            if log_event:
                EmailService.log_email(
                    to_email=to_email,
                    template_key=template_key,
                    subject='',
                    status='failed',
                    error_message=str(e),
                    user=user
                )
            return False

    @staticmethod
    def send_batch(emails: List[Dict]) -> Tuple[int, int]:
        """
        Send multiple emails.

        Args:
            emails: List of dicts with keys:
                - to_email: recipient email
                - template_key: template to use
                - context: template variables
                - user (optional): User to associate

        Returns:
            (sent_count, failed_count)
        """
        sent, failed = 0, 0
        for email_data in emails:
            if EmailService.send_email(**email_data):
                sent += 1
            else:
                failed += 1
        return sent, failed

    @staticmethod
    def log_email(
        to_email: str,
        template_key: str,
        subject: str,
        status: str = 'sent',
        error_message: str = '',
        user: Optional[User] = None
    ) -> None:
        """Log an email send attempt."""
        log_entry = {
            'to_email': to_email,
            'template_key': template_key,
            'subject': subject,
            'status': status,
            'error_message': error_message,
            'sent_at': timezone.now().isoformat()
        }

        # Store in AppSetting as rolling log
        logs_json = AppSetting.get('email_logs', '[]')
        try:
            logs = json.loads(logs_json) if isinstance(logs_json, str) else logs_json
        except (json.JSONDecodeError, TypeError):
            logs = []

        # Keep last 1000 logs
        logs.append(log_entry)
        logs = logs[-1000:]

        AppSetting.set('email_logs', json.dumps(logs))

    @staticmethod
    def get_logs(limit: int = 100) -> List[Dict]:
        """Get recent email logs."""
        logs_json = AppSetting.get('email_logs', '[]')
        try:
            logs = json.loads(logs_json) if isinstance(logs_json, str) else logs_json
        except (json.JSONDecodeError, TypeError):
            logs = []

        return logs[-limit:]


# Email template tags and placeholders
EMAIL_TAGS = {
    'employee_name': ('Employee Full Name', 'John Smith'),
    'employee_email': ('Employee Email', 'john@company.com'),
    'session_title': ('Session Title', 'Compliance Training'),
    'scheduled_date': ('Session Date', '2026-06-20'),
    'session_time': ('Session Time', '2:00 PM'),
    'duration_minutes': ('Duration in Minutes', '60'),
    'zoom_join_url': ('Zoom Meeting Link', 'https://zoom.us/j/123456789'),
    'description': ('Session Description', 'Important training session'),
    'quiz_title': ('Quiz Title', 'Compliance Quiz'),
    'score': ('Quiz Score', '95'),
    'passing_score': ('Passing Score', '80'),
    'status': ('Result Status', 'Passed'),
    'feedback': ('Quiz Feedback', 'Great job!'),
    'course_title': ('Course Title', 'New Hire Onboarding'),
    'course_description': ('Course Description', 'Complete onboarding program'),
    'course_link': ('Course Link', 'https://platform.com/courses/onboarding'),
    'start_date': ('Course Start Date', '2026-06-21'),
    'estimated_duration': ('Estimated Duration (hours)', '20'),
    'lesson_count': ('Number of Lessons', '10'),
    'completion_date': ('Completion Date', '2026-07-05'),
    'final_score': ('Final Score', '92'),
    'certificate_link': ('Certificate Link', 'https://platform.com/certificates/12345'),
    'time_until': ('Time Until Session', 'in 24 hours'),
    'rejection_reason': ('Rejection Reason', 'Requires further review'),
    'approval_deadline': ('Approval Deadline', '2026-06-25'),
}

EMAIL_TEMPLATE_DEFAULTS = set(DEFAULT_TEMPLATES.keys())


def upsert_custom_template(key: str, label: str, subject: str, body: str, user=None) -> bool:
    """Create or update a custom email template. Returns True if created (not updated)."""
    templates = EmailService.get_templates()
    is_new = key not in templates or templates[key].get('custom') is True

    # Prevent overwriting built-ins unless explicitly replacing
    if key in DEFAULT_TEMPLATES and key in templates and not templates[key].get('custom'):
        return False

    templates[key] = {
        'label': label,
        'subject': subject,
        'body': body,
        'custom': True,
    }
    EmailService.save_templates(templates)
    if user:
        log_activity(None, action="create_email_template" if is_new else "update_email_template",
                    entity_type="settings", description=f"Template: {label}")
    return is_new


def delete_custom_template(key: str, user=None) -> None:
    """Delete a custom email template."""
    templates = EmailService.get_templates()
    if key in templates and templates[key].get('custom'):
        del templates[key]
        EmailService.save_templates(templates)
        if user:
            log_activity(None, action="delete_email_template", entity_type="settings",
                        description=f"Deleted template: {key}")


def get_email_templates() -> Dict:
    """Get email templates (for editing)."""
    return EmailService.get_templates()


def save_email_templates(templates: Dict, user=None) -> None:
    """Save email templates."""
    EmailService.save_templates(templates)
    if user:
        log_activity(None, action="update_email_templates", entity_type="settings",
                    description="Updated email templates")


def all_email_templates() -> List[Dict]:
    """Get all templates with metadata for admin UI."""
    templates = EmailService.get_templates()
    return [
        {
            'key': k,
            'label': v.get('label', k.replace('_', ' ').title()),
            'subject': v.get('subject', ''),
            'body': v.get('body', ''),
            'custom': v.get('custom', False),
        }
        for k, v in templates.items()
    ]
