from datetime import datetime

from django.db import models
from django.utils import timezone
import secrets

# New offer-related models for Phase 1

class OfferFieldDefinition(models.Model):
    """Organization-level offer field definitions (configurable by admins).
    Example: Base Salary, Job Title, Equity, Signing Bonus.
    """
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, null=True, blank=True, related_name='offer_field_definitions')
    name = models.CharField(max_length=200)
    key = models.CharField(max_length=100)  # slug/key used in templates
    field_type = models.CharField(max_length=30, default='string')  # string, decimal, date, richtext, boolean, choice
    required = models.BooleanField(default=False)
    visible_to = models.JSONField(default=list, blank=True)  # e.g. ['sender','hrbp','admin']
    order = models.IntegerField(default=0)
    meta = models.JSONField(default=dict, blank=True)  # extra metadata (choices, currency, formatting)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'offer_field_definition'
        unique_together = ('tenant', 'key')
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.name} ({self.key})"


import bleach

class OfferTemplate(models.Model):
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, null=True, blank=True, related_name='offer_templates')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    html_content = models.TextField(blank=True)  # sanitized HTML
    plain_text_preview = models.TextField(blank=True)
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    is_default = models.BooleanField(default=False)
    variables_schema = models.JSONField(default=dict, blank=True)
    attachments_allowed = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'offer_template'
        ordering = ['-is_default', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Sanitize HTML before saving to prevent XSS. Allow tags useful for offers.
        allowed_tags = [
            'a', 'abbr', 'acronym', 'b', 'blockquote', 'br', 'code', 'div', 'em', 'i',
            'img', 'li', 'ol', 'p', 'pre', 'strong', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
            'ul', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span'
        ]
        allowed_attrs = {
            '*': ['style', 'class'],
            'a': ['href', 'title', 'target', 'rel'],
            'img': ['src', 'alt', 'title', 'width', 'height'],
            'td': ['colspan', 'rowspan'],
        }
        allowed_styles = ['text-align', 'float', 'width', 'height', 'color', 'background-color', 'font-weight', 'font-style', 'text-decoration']
        try:
            cleaned = bleach.clean(self.html_content or '', tags=allowed_tags, attributes=allowed_attrs, styles=allowed_styles, strip=True)
            self.html_content = cleaned
        except Exception:
            # On any bleach failure, fallback to stripping scripts
            self.html_content = bleach.clean(self.html_content or '', strip=True)
        super().save(*args, **kwargs)


class OfferEmailTemplate(models.Model):
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, null=True, blank=True, related_name='offer_email_templates')
    name = models.CharField(max_length=200)
    subject_template = models.CharField(max_length=400)
    html_body_template = models.TextField(blank=True)
    plain_text_template = models.TextField(blank=True)
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'offer_email_template'

    def __str__(self):
        return self.name


class Offer(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('revoked', 'Revoked'),
        ('expired', 'Expired'),
    ]

    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, null=True, blank=True, related_name='offers')
    template = models.ForeignKey(OfferTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    email_template = models.ForeignKey(OfferEmailTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name='offers_using_email_template')
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='offers_created')
    candidate_name = models.CharField(max_length=200)
    candidate_email = models.EmailField(max_length=200)
    candidate_user = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='offers_received')

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='draft')
    rendered_html = models.TextField(blank=True)
    rendered_email_html = models.TextField(blank=True)

    total_compensation = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    sent_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'offer'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['tenant', 'status']), models.Index(fields=['created_by'])]

    def __str__(self):
        return f"Offer {self.pk} to {self.candidate_email} [{self.status}]"

    @property
    def employee(self):
        return self.candidate_user

    @property
    def sent_by(self):
        return self.created_by

    @property
    def offer_number(self):
        return self.metadata.get("offer_number") or f"OFF-{self.pk:04d}"

    @property
    def offer_data(self):
        data = self.metadata or {}
        return data if isinstance(data, dict) else {}

    @property
    def expiry_date(self):
        value = self.metadata.get("expiry_date") if isinstance(self.metadata, dict) else None
        if not value:
            return None
        if hasattr(value, "tzinfo"):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None


class OfferFieldValue(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='field_values')
    field_definition = models.ForeignKey(OfferFieldDefinition, on_delete=models.SET_NULL, null=True, blank=True)
    value = models.TextField(blank=True)
    numeric_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    date_value = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'offer_field_value'

    def __str__(self):
        return f"{self.field_definition and self.field_definition.key}: {self.value}"


class OfferAttachment(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='attachments', null=True, blank=True)
    template = models.ForeignKey(OfferTemplate, on_delete=models.CASCADE, related_name='attachments_for_template', null=True, blank=True)
    file = models.FileField(upload_to='offer_attachments/')
    filename = models.CharField(max_length=255, null=True, blank=True)
    content_type = models.CharField(max_length=100, null=True, blank=True)
    size = models.IntegerField(null=True, blank=True)
    uploaded_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'offer_attachment'

    def __str__(self):
        return self.filename or (self.file.name if self.file else 'attachment')


class OfferStatusHistory(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='status_history')
    from_status = models.CharField(max_length=50)
    to_status = models.CharField(max_length=50)
    changed_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    reason = models.TextField(blank=True)
    comment = models.TextField(blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'offer_status_history'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.offer_id} {self.from_status}->{self.to_status} @ {self.timestamp}"


class OfferApproval(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='approvals')
    approver = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    order = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default='pending')  # pending, approved, rejected
    comment = models.TextField(blank=True)
    acted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'offer_approval'
        ordering = ['order']

    def __str__(self):
        return f"Approval {self.pk} for offer {self.offer_id} - {self.status}"


class OfferSignature(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='signatures')
    signer_name = models.CharField(max_length=200)
    signature_blob = models.TextField(blank=True)  # base64 or image path
    signature_method = models.CharField(max_length=50, default='typed')
    signed_at = models.DateTimeField(default=timezone.now)
    ip_address = models.CharField(max_length=45, blank=True)

    class Meta:
        db_table = 'offer_signature'

    def __str__(self):
        return f"Signature by {self.signer_name} on {self.signed_at}"


class OfferSendToken(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='tokens')
    token = models.CharField(max_length=128, unique=True, default=lambda: secrets.token_urlsafe(48))
    token_type = models.CharField(max_length=30, default='view')  # view, accept, reject
    expires_at = models.DateTimeField(null=True, blank=True)
    used = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'offer_send_token'

    def __str__(self):
        return f"Token {self.token_type} for offer {self.offer_id}"


class OfferExport(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='exports')
    export_type = models.CharField(max_length=20)
    storage_key = models.CharField(max_length=500)
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'offer_export'

    def __str__(self):
        return f"Export {self.export_type} for offer {self.offer_id}"


class OfferAuditLog(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=200)
    details = models.JSONField(default=dict, blank=True)
    performed_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'offer_audit_log'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action} on {self.timestamp}"


class OfferVisibility(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='visibility')
    user = models.ForeignKey('User', on_delete=models.CASCADE, null=True, blank=True)
    role = models.CharField(max_length=100, null=True, blank=True)
    permission_type = models.CharField(max_length=30, default='view')

    class Meta:
        db_table = 'offer_visibility'

    def __str__(self):
        return f"Visibility {self.permission_type} for {self.offer_id}" 
