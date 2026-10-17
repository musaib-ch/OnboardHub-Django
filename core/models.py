"""
OnboardHub — consolidated data model.

The original Flask app used 52 tables. This rebuild collapses them into
13 domain tables using JSON columns for the variable-shape data that
previously lived in many small satellite tables.

  1. Tenant            (was: tenant, tenant_feature, feature_module)
  2. User              (was: user, role, user_permission)
  3. OrgUnit           (was: department, organization_unit, organization_option, hrbp_department)
  4. AppSetting        (was: app_setting, integration_config, oracle_ebs_config)
  5. Form              (was: form, form_template, form_section, form_field, quiz, survey, assessment)
  6. FormResponse      (was: form_response, response, public_form_response, public_form_answer)
  7. OnboardingDocument(was: onboarding_document, onboarding_document_signature)
  8. MedicalRecord     (was: medical_requirement, medical_document, employee_medical_requirement)
  9. Notification      (was: notification, notification_email_log, local_mailbox_message, management_message)
 10. AuditLog          (was: audit_log, activity_log, sync_log)
 11. Content           (was: knowledge, training, orientation, presentation, portal_slider/gallery/video/resource)
 12. Engagement        (was: program, enrollment, training progress, timeline, goals, goal reviews, mentorship, mentor sessions)
 13. ReviewMessage     (was: management_message, stage_message, local_mailbox_message)
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────────────
# FILE VALIDATORS
# ─────────────────────────────────────────────────────────────────────────────
ALLOWED_FILE_EXTENSIONS = {
    'documents': ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf'],
    'images': ['jpg', 'jpeg', 'png', 'gif', 'svg', 'bmp'],
    'video': ['mp4', 'mov', 'webm', 'avi', 'flv', 'mkv'],
    'audio': ['mp3', 'wav', 'm4a', 'flac', 'aac'],
    'all': ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf', 'jpg', 'jpeg', 'png', 'gif', 'svg', 'bmp', 'mp4', 'mov', 'webm', 'avi', 'flv', 'mkv', 'mp3', 'wav', 'm4a', 'flac', 'aac']
}

def validate_file_extension(file, allowed=None):
    if allowed is None:
        allowed = ALLOWED_FILE_EXTENSIONS['all']
    ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''
    if ext not in allowed:
        raise ValidationError(f"File type '.{ext}' not allowed. Allowed: {', '.join(allowed)}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tenant
# ─────────────────────────────────────────────────────────────────────────────
class Tenant(models.Model):
    name = models.CharField(max_length=150)
    domain = models.CharField(max_length=255, unique=True, null=True, blank=True)
    subdomain = models.CharField(max_length=100, unique=True, null=True, blank=True)
    custom_domain = models.CharField(max_length=255, unique=True, null=True, blank=True)
    # {"medical": true, "goals": false, ...} — replaces tenant_feature / feature_module
    features = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "tenant"

    def feature_enabled(self, key: str) -> bool:
        return bool(self.features.get(key, True))

    def __str__(self):
        return self.name


# ─────────────────────────────────────────────────────────────────────────────
# 2. User  (custom — email login, role + permission overrides)
# ─────────────────────────────────────────────────────────────────────────────
ROLE_CHOICES = [
    ("super_admin", "Super Admin"),
    ("admin", "Admin"),
    ("hrbp", "HRBP"),
    ("medical_approver", "Medical Approver"),
    ("employee", "Employee"),
]

# Onboarding status state machine
STATUS_CHOICES = [
    ("pending", "Pending"),
    ("medical_upload", "Medical Upload"),
    ("medical_under_review", "Medical Under Review"),
    ("medical_info_requested", "Medical Info Requested"),
    ("medical_resubmission", "Medical Resubmission"),
    ("medical_rejected", "Medical Rejected"),
    ("pre_onboarding", "Pre-Onboarding"),
    ("pre_onboarding_submitted", "Pre-Onboarding Submitted"),
    ("pre_onboarding_resubmission", "Pre-Onboarding Resubmission"),
    ("pre_onboarding_info_requested", "Pre-Onboarding Info Requested"),
    ("pre_onboarding_rejected", "Pre-Onboarding Rejected"),
    ("onboarding", "Onboarding"),
    ("onboarding_submitted", "Onboarding Submitted"),
    ("onboarding_resubmission", "Onboarding Resubmission"),
    ("onboarding_info_requested", "Onboarding Info Requested"),
    ("onboarding_rejected", "Onboarding Rejected"),
    ("post_onboarding", "Post-Onboarding"),
    ("post_onboarding_submitted", "Post-Onboarding Submitted"),
    ("post_onboarding_resubmission", "Post-Onboarding Resubmission"),
    ("post_onboarding_info_requested", "Post-Onboarding Info Requested"),
    ("post_onboarding_rejected", "Post-Onboarding Rejected"),
    ("completed", "Completed"),
    ("on_hold", "On Hold"),
    ("archived", "Archived"),
    ("deleted", "Deleted"),
]


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).strip().lower()
        user = self.model(email=email, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("role", "super_admin")
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("full_name", email)
        extra.setdefault("status", "completed")
        extra.setdefault("must_change_password", False)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="users", null=True, blank=True
    )
    employee_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    full_name = models.CharField(max_length=100)
    avatar = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(max_length=120, unique=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    department = models.ForeignKey(
        "OrgUnit", on_delete=models.SET_NULL, related_name="members",
        null=True, blank=True,
    )
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default="employee")
    position_title = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="pending")
    employee_type = models.CharField(max_length=30, null=True, blank=True)
    grade = models.CharField(max_length=50, null=True, blank=True)
    location_code = models.CharField(max_length=255, null=True, blank=True)
    payroll = models.CharField(max_length=100, null=True, blank=True)

    # Per-user permission overrides (replaces user_permission table):
    # {"create_program": true, "approve_document": false}
    permissions_override = models.JSONField(default=dict, blank=True)

    # Scoping for HRBP / medical approver (replaces hrbp_department +
    # medical_approver_location tables):
    # {"departments": [orgunit_id, ...], "locations": ["Karachi", ...]}
    scope = models.JSONField(default=dict, blank=True)

    onboarding_token = models.CharField(max_length=255, unique=True, null=True, blank=True)
    onboarding_token_expires_at = models.DateTimeField(null=True, blank=True)
    password_reset_token = models.CharField(max_length=255, null=True, blank=True)
    password_reset_expires_at = models.DateTimeField(null=True, blank=True)

    progress_percentage = models.IntegerField(default=0)
    date_of_birth = models.DateField(null=True, blank=True)
    date_of_joining = models.DateField(null=True, blank=True)
    onboarding_unlock_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    # Stage timing for progress tracking (Phase 1: Due Dates)
    stage_entered_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When employee entered their current stage"
    )
    stage_due_date = models.DateTimeField(
        null=True, blank=True,
        help_text="Calculated due date for current stage (based on Stage.default_due_date_days)"
    )
    stage_due_date_override = models.DateTimeField(
        null=True, blank=True,
        help_text="If set, overrides the calculated due date (HR can customize per employee)"
    )

    # Configurable workflow: per-employee custom stage path (optional, falls back to global defaults)
    stage_path = models.OneToOneField(
        'EmployeeStagePath', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        help_text="If set, employee follows this custom stage path. Otherwise uses global defaults."
    )

    has_seen_welcome = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=True)
    enable_email_notifications = models.BooleanField(default=True)
    enable_in_app_notifications = models.BooleanField(default=True)
    # Granular notification preferences: {"session_invites": true, "reminders": true, ...}
    notification_preferences = models.JSONField(default=dict, blank=True)
    quiz_access_only = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="created_users"
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "user"

    # ── Permission resolution (role defaults + per-user overrides) ──────────
    def has_perm_key(self, permission_name: str) -> bool:
        if not permission_name or not self.role:
            return False
        if self.role == "super_admin":
            return True
        if permission_name in (self.permissions_override or {}):
            return bool(self.permissions_override[permission_name])
        from .permissions import resolve_role_permissions
        return permission_name in resolve_role_permissions(self.role)

    def effective_permissions(self):
        from .permissions import resolve_role_permissions, BASE_ROLE_PERMISSIONS
        if self.role == "super_admin":
            return sorted(BASE_ROLE_PERMISSIONS.get("super_admin", []))
        perms = set(resolve_role_permissions(self.role))
        for key, val in (self.permissions_override or {}).items():
            perms.add(key) if val else perms.discard(key)
        return sorted(perms)

    # ── Stage timing helpers (Phase 1: Due Dates) ─────────────────────────────
    def calculate_stage_due_date(self):
        """Calculate due date for current stage based on AppSetting stage config."""
        from . import pipeline
        if not self.stage_entered_at:
            return None
        try:
            current_stage = pipeline.stage_of_status(self.status)
            stages = AppSetting.get('stages', '{}')
            import json
            stages_dict = json.loads(stages) if isinstance(stages, str) else stages
            stage_config = stages_dict.get(current_stage, {})
            days = stage_config.get('default_due_date_days', 7)
            return self.stage_entered_at + timedelta(days=days)
        except (ValueError, KeyError):
            return None

    def get_effective_due_date(self):
        """Return override due date if set, otherwise calculated due date."""
        return self.stage_due_date_override or self.stage_due_date

    def is_stage_overdue(self):
        """Check if current stage is past due date."""
        due_date = self.get_effective_due_date()
        if not due_date:
            return False
        return timezone.now() > due_date

    def days_remaining_in_stage(self):
        """Days remaining until stage due date. Negative if overdue."""
        due_date = self.get_effective_due_date()
        if not due_date:
            return None
        delta = due_date - timezone.now()
        return delta.days

    def stage_status(self):
        """Get status badge for current stage (pending, in_progress, completed, overdue)."""
        from . import pipeline
        if self.status == "completed":
            return "completed"
        if self.is_stage_overdue():
            return "overdue"
        if self.stage_entered_at:
            return "in_progress"
        return "pending"

    # ── Password reset token helpers ────────────────────────────────────────
    def generate_password_reset_token(self, expires_in_seconds=3600):
        token = secrets.token_urlsafe(32)
        self.password_reset_token = token
        self.password_reset_expires_at = timezone.now() + timedelta(seconds=expires_in_seconds)
        return token

    def clear_password_reset_token(self):
        self.password_reset_token = None
        self.password_reset_expires_at = None

    def verify_password_reset_token(self, token):
        if not token or not self.password_reset_token:
            return False
        if self.password_reset_expires_at and self.password_reset_expires_at < timezone.now():
            return False
        return self.password_reset_token == token

    @property
    def display_name(self):
        return "Employee Unavailable" if self.status == "deleted" else self.full_name

    def __str__(self):
        return self.email


# ─────────────────────────────────────────────────────────────────────────────
# 3. OrgUnit  (departments, designations, locations, grades, employee types)
# ─────────────────────────────────────────────────────────────────────────────
class OrgUnit(models.Model):
    KIND_CHOICES = [
        ("department", "Department"),
        ("designation", "Designation"),
        ("location", "Location"),
        ("grade", "Grade"),
        ("payroll", "Payroll"),
        ("employee_type", "Employee Type"),
    ]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="org_units",
                               null=True, blank=True)
    kind = models.CharField(max_length=30, choices=KIND_CHOICES, default="department")
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="children")
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "org_unit"
        ordering = ["kind", "display_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.kind})"


# ─────────────────────────────────────────────────────────────────────────────
# 4. AppSetting  (key/value: theme, smtp, stage flags, integrations)
# ─────────────────────────────────────────────────────────────────────────────
class AppSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "app_setting"

    @classmethod
    def get(cls, key, default=None):
        row = cls.objects.filter(key=key).first()
        return row.value if row else default

    @classmethod
    def set(cls, key, value, user=None):
        cls.objects.update_or_create(
            key=key, defaults={"value": value, "updated_by": user}
        )

    def __str__(self):
        return self.key


# ─────────────────────────────────────────────────────────────────────────────
# 5. Form  (form + sections + fields collapsed into a JSON schema)
# ─────────────────────────────────────────────────────────────────────────────
class Form(models.Model):
    """
    `schema` holds the full structure:
      {"sections": [
          {"title": "...", "description": "...",
           "fields": [
              {"id": "f1", "label": "...", "field_name": "...", "field_type": "text",
               "is_required": true, "options": [...], "placeholder": "...",
               "help_text": "...", "conditional_logic": {...}}
           ]}
      ]}
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="forms",
                               null=True, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    # purpose: onboarding stage OR quiz/survey/assessment
    stage = models.CharField(max_length=50, db_index=True)
    form_kind = models.CharField(
        max_length=20,
        choices=[("form", "Form"), ("quiz", "Quiz"), ("survey", "Survey")],
        default="form",
    )
    employee_type = models.CharField(max_length=30, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    theme_color = models.CharField(max_length=20, default="#0078D4")
    collect_responses = models.BooleanField(default=True)
    is_anonymous = models.BooleanField(default=False)
    allow_multiple_submissions = models.BooleanField(default=False)
    show_progress_bar = models.BooleanField(default=True)
    shuffle_questions = models.BooleanField(default=False)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    share_token = models.CharField(max_length=32, unique=True, null=True, blank=True)
    schema = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "form"
        ordering = ["display_order", "id"]

    def get_all_fields(self):
        fields = []
        for sec in self.schema.get("sections", []):
            fields.extend(sec.get("fields", []))
        return fields

    def required_field_names(self):
        return [f["field_name"] for f in self.get_all_fields() if f.get("is_required")]

    def get_signable_fields(self):
        signable_types = {"pdf_sign", "doc_sign", "policy_sign", "ppt_view"}
        return [f for f in self.get_all_fields() if f.get("field_type") in signable_types or f.get("requires_signature")]

    def has_documents(self):
        return bool(self.get_signable_fields())

    def generate_share_token(self):
        if not self.share_token:
            self.share_token = secrets.token_urlsafe(16)[:32]
        return self.share_token

    @property
    def share_url(self):
        return f"/public/form/{self.share_token}" if self.share_token else None

    def __str__(self):
        return self.name


# ─────────────────────────────────────────────────────────────────────────────
# 6. FormResponse  (one row per submission; answers stored as JSON)
# ─────────────────────────────────────────────────────────────────────────────
class FormResponse(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="responses")
    employee = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="form_responses",
        null=True, blank=True,
    )
    # {"field_name": "value", ...}
    answers = models.JSONField(default=dict, blank=True)
    # {"field_name": "uploads/..."} for file fields
    files = models.JSONField(default=dict, blank=True)
    is_draft = models.BooleanField(default=True)
    score = models.FloatField(null=True, blank=True)  # for quizzes

    # public (anonymous) submission metadata
    respondent_name = models.CharField(max_length=200, null=True, blank=True)
    respondent_email = models.CharField(max_length=200, null=True, blank=True)
    ip_address = models.CharField(max_length=45, null=True, blank=True)

    submitted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "form_response"
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"Response #{self.pk} to {self.form_id}"


# ─────────────────────────────────────────────────────────────────────────────
# 7. OnboardingDocument  (+ signatures stored as JSON list)
# ─────────────────────────────────────────────────────────────────────────────
class OnboardingDocument(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    stage = models.CharField(max_length=50, db_index=True)
    file = models.FileField(upload_to="onboarding/", null=True, blank=True)
    body = models.TextField(null=True, blank=True)  # inline HTML doc
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    # [{"employee_id": 1, "signed_at": "...", "signature": "..."}]
    signatures = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "onboarding_document"
        ordering = ["display_order", "id"]

    def signed_by(self, employee_id) -> bool:
        return any(s.get("employee_id") == employee_id for s in self.signatures)

    def __str__(self):
        return self.title


# ─────────────────────────────────────────────────────────────────────────────
# 8. MedicalRecord  (requirement catalog + per-employee submission/review)
# ─────────────────────────────────────────────────────────────────────────────
class MedicalRecord(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    # When employee is null this row is a requirement catalog entry (a template).
    employee = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="medical_records",
        null=True, blank=True,
    )
    requirement_name = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    is_required = models.BooleanField(default=True)
    is_catalog = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # Applicability rule for catalog tests: {"gender": "male", "min_age": 40}
    meta = models.JSONField(default=dict, blank=True)
    file = models.FileField(upload_to="medical/", null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=[
            ("pending", "Pending"), ("uploaded", "Uploaded"),
            ("under_review", "Under Review"), ("approved", "Approved"),
            ("rejected", "Rejected"), ("info_requested", "Info Requested"),
        ],
        default="pending",
    )
    review_notes = models.TextField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="medical_reviews"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "medical_record"
        ordering = ["id"]

    def __str__(self):
        return f"{self.requirement_name} ({self.status})"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Notification  (+ email log fields)
# ─────────────────────────────────────────────────────────────────────────────
class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    message = models.TextField(null=True, blank=True)
    link = models.CharField(max_length=500, null=True, blank=True)
    category = models.CharField(max_length=50, default="info")
    is_read = models.BooleanField(default=False)
    email_sent = models.BooleanField(default=False)
    email_error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "notification"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


# ─────────────────────────────────────────────────────────────────────────────
# 10. AuditLog  (audit + activity + sync logs)
# ─────────────────────────────────────────────────────────────────────────────
class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="audit_logs")
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=50, null=True, blank=True)
    entity_id = models.IntegerField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    ip_address = models.CharField(max_length=45, null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "audit_log"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.action} @ {self.timestamp:%Y-%m-%d %H:%M}"


# ─────────────────────────────────────────────────────────────────────────────
# 11. Content  (knowledge / training / orientation / presentation / portal CMS)
# ─────────────────────────────────────────────────────────────────────────────
class Content(models.Model):
    KIND_CHOICES = [
        ("knowledge", "Knowledge Article"),
        ("training", "Training Module"),
        ("learning_path", "Learning Path"),
        ("onboarding_plan", "Onboarding Plan Template"),
        ("orientation", "Orientation Session"),
        ("presentation", "Presentation"),
        ("portal_slider", "Portal Slider"),
        ("portal_gallery", "Portal Gallery"),
        ("portal_video", "Portal Video"),
        ("portal_resource", "Portal Resource"),
        ("management_message", "Management Message"),
        ("news", "News"),
        ("event", "Event"),
    ]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    kind = models.CharField(max_length=30, choices=KIND_CHOICES, db_index=True)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=120, null=True, blank=True)
    body = models.TextField(null=True, blank=True)
    file = models.FileField(upload_to="content/", null=True, blank=True)
    # flexible per-kind data: {"sections": [...], "duration": 30, "video_url": "..."}
    meta = models.JSONField(default=dict, blank=True)

    # ── Phase 3.2: Content Variants (Filtering) ──
    # Target audience filters (leave empty = all employees)
    target_roles = models.JSONField(default=list, blank=True, help_text="Roles: admin, hrbp, manager, employee (empty = all)")
    target_locations = models.JSONField(default=list, blank=True, help_text="Location IDs (empty = all)")
    target_departments = models.JSONField(default=list, blank=True, help_text="Department IDs (empty = all)")
    target_divisions = models.JSONField(default=list, blank=True, help_text="Division IDs (empty = all)")

    # Required before access (sequential unlock)
    prerequisite_content = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='unlocks')
    sequence_order = models.IntegerField(default=0, help_text="Order in learning path")

    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "content"
        ordering = ["kind", "display_order", "-created_at"]

    def __str__(self):
        return f"[{self.kind}] {self.title}"


# ─────────────────────────────────────────────────────────────────────────────
# 12. Engagement  (programs/enrollment + goals + mentorship — kind-differentiated)
# ─────────────────────────────────────────────────────────────────────────────
class Engagement(models.Model):
    """One table for per-employee development records.

    Consolidates the former Enrollment, Goal and Mentorship tables; the `kind`
    column differentiates them and `data` (JSON) holds the variable-shape parts
    (completed sections, goal milestones/reviews, mentorship sessions).
    """
    KIND_CHOICES = [
        ("enrollment", "Program / Training Enrollment"),
        ("onboarding_plan", "Onboarding Plan"),
        ("goal", "Goal"),
        ("mentorship", "Mentorship"),
        ("chat_dm", "Direct Message Chat"),
    ]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, db_index=True)
    # Owner: the enrollee / goal-owner / mentor.
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="engagements")
    # Counterparty: the goal's manager / the mentee. Null for enrollments.
    counterparty = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="engagement_counterparts",
    )
    content = models.ForeignKey(Content, on_delete=models.CASCADE, null=True, blank=True,
                                related_name="engagements")
    title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=30, default="active")
    progress = models.IntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    # enrollment: {"completed_sections": [...]}; goal: {"milestones": [...], "reviews": [...]};
    # mentorship: {"sessions": [...]}
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "engagement"
        ordering = ["kind", "-created_at"]

    def __str__(self):
        return f"[{self.kind}] {self.title or self.pk}"


# ─────────────────────────────────────────────────────────────────────────────
# 13. ReviewMessage  (reviewer ↔ employee conversation per stage)
# ─────────────────────────────────────────────────────────────────────────────
class ReviewMessage(models.Model):
    """Reviewer ↔ employee conversation, scoped to an onboarding stage.

    Replaces the original management_message / stage_message thread tables.
    """
    KIND_CHOICES = [
        ("message", "Message"),
        ("info_request", "Information Request"),
        ("changes", "Changes Requested"),
        ("rejection", "Rejection"),
        ("reply", "Employee Reply"),
    ]
    employee = models.ForeignKey(User, on_delete=models.CASCADE, related_name="review_messages")
    stage = models.CharField(max_length=50)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="authored_review_messages")
    # When set, the message is about ONE medical test row (shown only there).
    medical_record = models.ForeignKey(
        "MedicalRecord", on_delete=models.CASCADE, null=True, blank=True,
        related_name="messages",
    )
    message = models.TextField()
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="message")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "review_message"
        ordering = ["created_at"]

    @property
    def from_employee(self):
        return self.author_id == self.employee_id

    def __str__(self):
        return f"{self.kind} on {self.stage} for {self.employee_id}"


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURABLE WORKFLOW SYSTEM — Stage definitions, templates, paths
# ─────────────────────────────────────────────────────────────────────────────

class StageDefinition(models.Model):
    """Database-driven stage configuration (replaces hardcoded STAGE_ORDER)."""
    STAGE_TYPE_CHOICES = [
        ("mandatory", "Mandatory - all employees"),
        ("optional", "Optional - depends on employee type/role"),
        ("conditional", "Conditional - based on organization/department"),
    ]

    stage_key = models.CharField(max_length=50, unique=True, db_index=True)
    label = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    is_enabled = models.BooleanField(default=True, db_index=True)
    is_mandatory = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    default_due_date_days = models.IntegerField(default=7)
    approval_role = models.CharField(max_length=50, blank=True)
    stage_type = models.CharField(max_length=20, choices=STAGE_TYPE_CHOICES, default="mandatory")

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        db_table = "stage_definition"
        ordering = ['order']
        indexes = [
            models.Index(fields=['stage_key']),
            models.Index(fields=['is_enabled']),
        ]

    def __str__(self):
        return f"{self.label} ({self.stage_key})"


class StageTemplate(models.Model):
    """Pre-built workflow templates (Standard Onboarding, Contractor, etc.)."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    stages = models.JSONField(default=list, blank=True)  # Uses list as callable

    is_global = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        db_table = "stage_template"
        ordering = ['name']

    def __str__(self):
        return self.name


class EmployeeStagePath(models.Model):
    """Per-employee custom workflow path."""
    employee = models.OneToOneField(User, on_delete=models.CASCADE, related_name='_stage_path', db_index=True)

    stages = models.JSONField(default=list)

    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    modified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    change_reason = models.TextField(blank=True)

    class Meta:
        db_table = "employee_stage_path"

    def __str__(self):
        return f"{self.employee.email} - {len(self.stages)} stages"


class OfferWorkflow(models.Model):
    """Offer Acceptance stage workflow."""
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("viewed", "Viewed"),
        ("signed", "Signed - Pending Acceptance"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("expired", "Expired"),
    ]

    employee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='offers')

    offer_number = models.CharField(max_length=50, unique=True)
    offer_template = models.ForeignKey(Form, on_delete=models.SET_NULL, null=True, blank=True)

    sent_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="offers_sent")
    sent_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    viewed_at = models.DateTimeField(null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    signed_by_name = models.CharField(max_length=100, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    offer_data = models.JSONField(default=dict)
    expiry_date = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "offer_workflow"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['sent_by']),
        ]

    def __str__(self):
        return f"{self.offer_number} - {self.status}"

from .models_offers import *
