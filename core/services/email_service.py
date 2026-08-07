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


def _big_login_cta(url: str) -> str:
    return f"""
<div class="login-cta">
  <p>Click the button below to access your portal</p>
  <a href="{url}">Go to OnboardHub &rarr;</a>
  <p class="login-url">{url}</p>
</div>"""

def _small_portal_link(url: str, label: str = "Go to Portal ->") -> str:
    return f"""
<div class="portal-link">
  <a href="{url}">{label}</a>
</div>"""


# Default email templates - stored in AppSetting['email_templates']
DEFAULT_TEMPLATES = {
    'welcome_employee': {
        'subject': 'Welcome to OnboardHub - Your Account is Ready',
        'title': 'Welcome Aboard!',
        'body': """
<p>Hi <strong>{{full_name}}</strong>,</p>
<p>Welcome! Your onboarding account has been created on <strong>OnboardHub</strong>.
Use the credentials below to log in and begin your onboarding journey.</p>
<div class="cred-box">
  <p><span class="label">Email</span><br><span class="val">{{email}}</span></p>
  <p style="margin-top:12px"><span class="label">Temporary Password</span><br><span class="val">{{temp_password}}</span></p>
</div>
<p>You will be asked to set a new password on your first login.</p>
{{big_login_cta|safe}}
<hr class="divider">
<p style="color:#6b7280;font-size:.85rem;">
  Your onboarding has a few steps: Medical document upload -> Pre-Onboarding forms -> Onboarding documents.
</p>""".strip(),
    },
    'welcome_admin': {
        'subject': 'OnboardHub - Your Account Has Been Created',
        'title': 'Your {{role_label}} Account',
        'body': """
<p>Hi <strong>{{full_name}}</strong>,</p>
<p>An <strong>OnboardHub</strong> portal account has been created for you with role
<span class="badge badge-info">{{role_label}}</span>.</p>
<div class="cred-box">
  <p><span class="label">Email</span><br><span class="val">{{email}}</span></p>
  <p style="margin-top:12px"><span class="label">Temporary Password</span><br><span class="val">{{temp_password}}</span></p>
</div>
<p>You will be asked to set a new password on your first login.</p>
{{big_login_cta|safe}}""".strip(),
    },
    'credentials_reset': {
        'subject': 'OnboardHub - Your Login Credentials Have Been Reset',
        'title': 'Login Credentials Reset',
        'body': """
<p>Hi <strong>{{full_name}}</strong>,</p>
<p>Your OnboardHub login credentials have been reset by an administrator.
Use the details below to sign in.</p>
<div class="cred-box">
  <p><span class="label">Email</span><br><span class="val">{{email}}</span></p>
  <p style="margin-top:12px"><span class="label">Temporary Password</span><br><span class="val">{{temp_password}}</span></p>
</div>
<p>You will be asked to set a new password immediately after login.</p>
{{big_login_cta|safe}}""".strip(),
    },
    'offer_sent': {
        'subject': 'OnboardHub - Your Offer Letter Is Ready',
        'title': 'Your Offer Is Ready',
        'body': """
<p>Hi <strong>{{full_name}}</strong>,</p>
<p>We are pleased to share your offer for <strong>{{position_title}}</strong>.</p>
<div class="cred-box"><p><span class="label">Salary</span><br><span class="val">{{salary}}</span></p><p style="margin-top:12px"><span class="label">Proposed start date</span><br><span class="val">{{start_date}}</span></p><p style="margin-top:12px"><span class="label">Reply by</span><br><span class="val">{{expiry_date}}</span></p></div>
<p>Please sign in to review and accept or decline the offer.</p>
{{big_login_cta|safe}}""".strip(),
    },
    'medical_approved': {
        'subject': 'OnboardHub - Medical Documents Approved',
        'title': 'Medical Documents Approved',
        'body': """
<p>Hi <strong>{{full_name}}</strong>,</p>
<p>Great news! Your medical documents have been <span class="badge badge-success">Approved</span>.</p>
<p>You can now proceed to the <strong>Pre-Onboarding Forms</strong> stage.</p>
{{small_portal_link_onboarding|safe}}
<hr class="divider">
<p style="color:#6b7280;font-size:.85rem;">
  Next step: Fill in your details in the Pre-Onboarding Forms section.
</p>""".strip(),
    },
    'medical_rejected': {
        'subject': 'OnboardHub - Medical Documents Rejected',
        'title': 'Medical Documents Rejected',
        'body': """
<p>Hi <strong>{{full_name}}</strong>,</p>
<p>One or more of your medical documents have been
<span class="badge badge-danger">Rejected</span>.</p>
{{remarks_html|safe}}
<p>Please contact HR for further information.</p>
{{small_portal_link_view|safe}}""".strip(),
    },
    'pre_onboarding_approved': {
        'subject': 'OnboardHub - Pre-Onboarding Approved',
        'title': 'Pre-Onboarding Approved',
        'body': """
<p>Hi <strong>{{full_name}}</strong>,</p>
<p>Your Pre-Onboarding forms have been reviewed and
<span class="badge badge-success">Approved</span>.</p>
<p>You can now proceed to the <strong>Onboarding Documents</strong> stage.</p>
{{small_portal_link_continue_docs|safe}}""".strip(),
    },
    'pre_onboarding_rejected': {
        'subject': 'OnboardHub - Pre-Onboarding Rejected',
        'title': 'Pre-Onboarding Rejected',
        'body': """
<p>Hi <strong>{{full_name}}</strong>,</p>
<p>Your Pre-Onboarding form submission has been
<span class="badge badge-danger">Rejected</span>.</p>
{{reason_html|safe}}
<p>Please contact HR for further information.</p>
{{small_portal_link_view|safe}}""".strip(),
    },
    'account_on_hold': {
        'subject': 'OnboardHub - Your Account is on Hold',
        'title': 'Account Placed on Hold',
        'body': """
<p>Hi <strong>{{full_name}}</strong>,</p>
<p>Your OnboardHub portal access has been temporarily
<span class="badge badge-warning">Placed on Hold</span>.</p>
<p>You will not be able to log in until your account is reactivated.
Please contact HR for more information.</p>""".strip(),
    },
    'account_activated': {
        'subject': 'OnboardHub - Your Account Has Been Reactivated',
        'title': 'Account Reactivated',
        'body': """
<p>Hi <strong>{{full_name}}</strong>,</p>
<p>Your OnboardHub portal account has been
<span class="badge badge-success">Reactivated</span>.</p>
<p>You can now log in and continue your onboarding from where you left off.</p>
{{small_portal_link_return|safe}}""".strip(),
    },
    'resubmission_requested': {
        'subject': 'OnboardHub - Resubmission Required: {{stage_label}}',
        'title': 'Resubmission Required - {{stage_label}}',
        'body': """
<p>Hi <strong>{{full_name}}</strong>,</p>
<p>Your <strong>{{stage_label}}</strong> have been reviewed and a
<span class="badge badge-warning">Resubmission</span> is required.</p>
<div class="cred-box" style="border-color:#fbbf24;background:#fffbeb;">
  <p><span class="label">Reviewer's Message</span><br>{{message}}</p>
</div>
<p>Please review the feedback and resubmit the required information.</p>
{{small_portal_link_stage|safe}}""".strip(),
    },
    'medical_submitted': {
        'subject': 'OnboardHub - Medical Documents Submitted: {{employee_name}}',
        'title': 'Medical Review Required',
        'body': """
<p>The employee <strong>{{employee_name}}</strong> ({{employee_email}}) has submitted their medical documents for review.</p>
<p>Please log in to the portal to review the submission.</p>
{{small_portal_link_review|safe}}""".strip(),
    },
    'pre_onboarding_submitted': {
        'subject': 'OnboardHub - Pre-Onboarding Submitted: {{employee_name}}',
        'title': 'Pre-Onboarding Review Required',
        'body': """
<p>The employee <strong>{{employee_name}}</strong> ({{employee_email}}) from <strong>{{department}}</strong> has submitted their pre-onboarding forms.</p>
<p>Please log in to the portal to review the details and approve or request changes.</p>
{{small_portal_link_review|safe}}""".strip(),
    },
    'onboarding_docs_submitted': {
        'subject': 'OnboardHub - Onboarding Documents Signed: {{employee_name}}',
        'title': 'Onboarding Documents Completed',
        'body': """
<p>The employee <strong>{{employee_name}}</strong> ({{employee_email}}) from <strong>{{department}}</strong> has completed signing all required onboarding documents.</p>
{{small_portal_link_review|safe}}""".strip(),
    },
    'session_invitation': {
        'subject': 'You\'re invited to {{session_title}}',
        'title': 'Session Invitation',
        'body': '''<p>Hi <strong>{{employee_name}}</strong>,</p>
<p>You've been invited to attend <strong>{{session_title}}</strong>.</p>
<div class="cred-box">
  <p><span class="label">Date</span><br><span class="val">{{scheduled_date}}</span></p>
  <p style="margin-top:12px"><span class="label">Duration</span><br><span class="val">{{duration_minutes}} minutes</span></p>
  <p style="margin-top:12px"><span class="label">Meeting Link</span><br><span class="val"><a href="{{zoom_join_url}}">Join Meeting</a></span></p>
</div>
<p>{{description}}</p>
<p>Please confirm your attendance by {{approval_deadline}}.</p>'''
    },
    'quiz_results': {
        'subject': 'Quiz Results: {{quiz_title}}',
        'title': 'Quiz Results',
        'body': '''<p>Hi <strong>{{employee_name}}</strong>,</p>
<p>You've completed the quiz: <strong>{{quiz_title}}</strong></p>
<div class="cred-box">
  <p><span class="label">Your Score</span><br><span class="val">{{score}}%</span></p>
  <p style="margin-top:12px"><span class="label">Status</span><br><span class="val">{{status}}</span></p>
  <p style="margin-top:12px"><span class="label">Passing Score</span><br><span class="val">{{passing_score}}%</span></p>
</div>
<p>{{feedback}}</p>'''
    },
    'course_enrollment': {
        'subject': 'You\'ve been enrolled in {{course_title}}',
        'title': 'Course Enrollment',
        'body': '''<p>Hi <strong>{{employee_name}}</strong>,</p>
<p>You've been enrolled in the learning path: <strong>{{course_title}}</strong></p>
<div class="cred-box">
  <p><span class="label">Start Date</span><br><span class="val">{{start_date}}</span></p>
  <p style="margin-top:12px"><span class="label">Duration</span><br><span class="val">{{estimated_duration}} hours</span></p>
  <p style="margin-top:12px"><span class="label">Lessons</span><br><span class="val">{{lesson_count}}</span></p>
</div>
<p>{{course_description}}</p>
{{small_portal_link_course|safe}}'''
    },
    'survey_assigned': {
        'subject': 'OnboardHub - New Survey Assigned: {{survey_title}}',
        'title': 'New Survey Assigned',
        'body': '''<p>Hi <strong>{{employee_name}}</strong>,</p>
<p>A new survey <strong>{{survey_title}}</strong> has been assigned to you.</p>
<p>We value your feedback to help us improve the onboarding experience.</p>
{{small_portal_link_survey|safe}}'''
    },
    'medical_stage_welcome': {
        'subject': 'OnboardHub - Action Required: Medical Documents',
        'title': 'Medical Documents Stage',
        'body': '''<p>Hi <strong>{{employee_name}}</strong>,</p>
<p>You have reached the <strong>Medical Documents</strong> stage of your onboarding.</p>
<p>Please log in to your portal and upload the required medical forms for review.</p>
{{small_portal_link_onboarding|safe}}'''
    },
    'pre_onboarding_welcome': {
        'subject': 'OnboardHub - Action Required: Pre-Onboarding',
        'title': 'Pre-Onboarding Stage',
        'body': '''<p>Hi <strong>{{employee_name}}</strong>,</p>
<p>You have reached the <strong>Pre-Onboarding</strong> stage.</p>
<p>We need you to complete a few forms before your start date. Please log in to fill them out.</p>
{{small_portal_link_onboarding|safe}}'''
    },
    'onboarding_welcome': {
        'subject': 'OnboardHub - Action Required: Onboarding Documents',
        'title': 'Onboarding Documents Stage',
        'body': '''<p>Hi <strong>{{employee_name}}</strong>,</p>
<p>You are now in the final <strong>Onboarding Documents</strong> stage!</p>
<p>Please review and sign your final onboarding documents in the portal.</p>
{{small_portal_link_onboarding|safe}}'''
    },
}

class EmailService:
    """Service for sending templated emails with logging."""

    @staticmethod
    def _wrap(title: str, body: str) -> str:
        def _normalize_color(value: str, fallback: str) -> str:
            raw = (value or "").strip()
            if raw.lower() == "white":
                return "#ffffff"
            if raw.lower() == "black":
                return "#111111"
            raw = raw.lstrip("#")
            if len(raw) == 3 and all(ch in "0123456789abcdefABCDEF" for ch in raw):
                raw = "".join(ch * 2 for ch in raw)
            if len(raw) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in raw):
                return f"#{raw.lower()}"
            return fallback

        site_title = (AppSetting.get("site_title", "") or "OnboardHub").strip() or "OnboardHub"
        primary = _normalize_color(AppSetting.get("primary_color", ""), "#1d2b4f")
        accent = _normalize_color(AppSetting.get("accent_color", ""), "#324b8a")
        nav_text = _normalize_color(AppSetting.get("nav_text_color", ""), "#ffffff")
        page_bg = _normalize_color(AppSetting.get("page_bg_color", ""), "#f8fafc")

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: {page_bg}; margin: 0; padding: 0; -webkit-font-smoothing: antialiased; }}
  .container {{ padding: 40px 20px; }}
  .wrap {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 24px; box-shadow: 0 12px 32px rgba(0,0,0,0.06), 0 2px 8px rgba(0,0,0,0.03); overflow: hidden; border: 1px solid rgba(0,0,0,0.04); }}
  .header {{ background: linear-gradient(135deg, {primary} 0%, {accent} 100%); padding: 48px 40px; text-align: center; }}
  .header h1 {{ color: {nav_text}; margin: 0; font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; }}
  .header p  {{ color: rgba(255,255,255,0.85); margin: 8px 0 0; font-size: 0.95rem; font-weight: 500; }}
  .body {{ padding: 40px; color: #334155; line-height: 1.7; font-size: 1rem; }}
  .body h2 {{ color: #0f172a; font-size: 1.35rem; font-weight: 700; margin-top: 0; margin-bottom: 24px; letter-spacing: -0.01em; }}
  .body p {{ margin-top: 0; margin-bottom: 16px; }}
  .cred-box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px; margin: 28px 0; }}
  .cred-box p {{ margin: 0; font-size: 0.95rem; }}
  .cred-box .label {{ color: #64748b; font-size: 0.75rem; text-transform: uppercase; font-weight: 700; letter-spacing: 0.06em; margin-bottom: 4px; display: block; }}
  .cred-box .val {{ color: #0f172a; font-weight: 600; font-size: 1.05rem; display: block; }}
  .login-cta {{ text-align: center; margin: 36px 0; }}
  .login-cta a {{ display: inline-block; background: {primary}; color: #ffffff !important; text-decoration: none; padding: 14px 36px; border-radius: 100px; font-size: 1rem; font-weight: 600; box-shadow: 0 4px 14px {accent}40; transition: transform 0.2s, box-shadow 0.2s; }}
  .login-cta p {{ color: #64748b; font-size: 0.85rem; margin-top: 16px; }}
  .login-url {{ font-size: 0.8rem; color: #94a3b8; word-break: break-all; margin-top: 8px; }}
  .badge {{ display: inline-block; padding: 6px 14px; border-radius: 100px; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.01em; }}
  .badge-success {{ background: #ecfdf5; color: #059669; border: 1px solid #d1fae5; }}
  .badge-danger  {{ background: #fef2f2; color: #dc2626; border: 1px solid #fee2e2; }}
  .badge-warning {{ background: #fffbeb; color: #d97706; border: 1px solid #fef3c7; }}
  .badge-info    {{ background: #eff6ff; color: #2563eb; border: 1px solid #dbeafe; }}
  .divider {{ border: none; border-top: 1px solid #e2e8f0; margin: 32px 0; }}
  .portal-link {{ text-align: center; margin: 28px 0; }}
  .portal-link a {{ color: {primary}; font-weight: 600; text-decoration: none; font-size: 1rem; border-bottom: 2px solid {accent}40; padding-bottom: 2px; }}
  .footer {{ background: #f8fafc; border-top: 1px solid #f1f5f9; padding: 32px 40px; color: #94a3b8; font-size: 0.85rem; text-align: center; }}
</style>
</head>
<body>
<div class="container">
  <div class="wrap">
    <div class="header">
      <h1>{site_title}</h1>
      <p>Employee Experience Portal</p>
    </div>
    <div class="body">
      <h2>{title}</h2>
      {body}
    </div>
    <div class="footer">
      <p style="margin:0;">This is an automated message from <strong>{site_title}</strong>.</p>
      <p style="margin:8px 0 0 0;">Please do not reply to this email.</p>
    </div>
  </div>
</div>
</body>
</html>"""

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
    def render_template(template_key: str, context: Dict) -> Tuple[str, str, str]:
        """
        Render a template with given context variables.

        Returns: (subject, title, body)
        """
        template = EmailService.get_template(template_key)
        if not template:
            raise ValueError(f'Template "{template_key}" not found')

        subject_tpl = Template(template.get('subject', ''))
        title_tpl = Template(template.get('title', ''))
        body_tpl = Template(template.get('body', ''))

        ctx = Context(context)
        subject = subject_tpl.render(ctx)
        title = title_tpl.render(ctx)
        body = body_tpl.render(ctx)

        return subject, title, body

    @staticmethod
    def send_email(
        to_email: str,
        template_key: str,
        context: Dict,
        from_email: Optional[str] = None,
        log_event: bool = True,
        user: Optional[User] = None
    ) -> bool:
        try:
            # Get SMTP config
            from_email = from_email or AppSetting.get('smtp_from_email', settings.DEFAULT_FROM_EMAIL)

            # Render template
            subject, title, body = EmailService.render_template(template_key, context)
            
            # Wrap into HTML
            html_message = EmailService._wrap(title, body)

            # Send email
            send_mail(
                subject=subject,
                message=body, # plain text fallback
                from_email=from_email,
                recipient_list=[to_email],
                fail_silently=False,
                html_message=html_message
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
    def send_raw_html(
        to_email: str,
        subject: str,
        html_message: str,
        from_email: Optional[str] = None,
        log_event: bool = True,
        user: Optional[User] = None
    ) -> bool:
        """Send a pre-rendered HTML email (no template rendering)."""
        try:
            from_email = from_email or AppSetting.get('smtp_from_email', settings.DEFAULT_FROM_EMAIL)
            send_mail(
                subject=subject,
                message='',
                from_email=from_email,
                recipient_list=[to_email],
                fail_silently=False,
                html_message=html_message
            )
            if log_event:
                EmailService.log_email(
                    to_email=to_email,
                    template_key='raw_html',
                    subject=subject,
                    status='sent',
                    user=user
                )
            logger.info(f'Raw HTML email sent to {to_email}')
            return True
        except Exception as e:
            logger.error(f'Failed to send raw HTML email to {to_email}: {str(e)}')
            if log_event:
                EmailService.log_email(
                    to_email=to_email,
                    template_key='raw_html',
                    subject=subject,
                    status='failed',
                    error_message=str(e),
                    user=user
                )
            return False

    @staticmethod
    def send_batch(emails: List[Dict]) -> Tuple[int, int]:
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

        logs.append(log_entry)
        logs = logs[-1000:]

        AppSetting.set('email_logs', json.dumps(logs))

    @staticmethod
    def get_logs(limit: int = 100) -> List[Dict]:
        logs_json = AppSetting.get('email_logs', '[]')
        try:
            logs = json.loads(logs_json) if isinstance(logs_json, str) else logs_json
        except (json.JSONDecodeError, TypeError):
            logs = []

        return logs[-limit:]

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
    templates = EmailService.get_templates()
    is_new = key not in templates or templates[key].get('custom') is True

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
    templates = EmailService.get_templates()
    if key in templates and templates[key].get('custom'):
        del templates[key]
        EmailService.save_templates(templates)
        if user:
            log_activity(None, action="delete_email_template", entity_type="settings",
                        description=f"Deleted template: {key}")

def get_email_templates() -> Dict:
    return EmailService.get_templates()

def save_email_templates(templates: Dict, user=None) -> None:
    EmailService.save_templates(templates)
    if user:
        log_activity(None, action="update_email_templates", entity_type="settings",
                    description="Updated email templates")

def all_email_templates() -> List[Dict]:
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
