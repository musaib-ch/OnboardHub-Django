"""
E-Signature model for document signing.

Tracks signature events, signer information, and signature metadata.
"""
from django.db import models
from django.utils import timezone
from django.core.validators import URLValidator
import uuid


class DocumentSignature(models.Model):
    """
    Record of a document signature event.

    Fields:
    - document_id: FK to onboarding_document
    - user: FK to User (signer)
    - signature_image: Base64-encoded PNG/SVG of signature
    - ip_address: IP address where signature was created
    - user_agent: Browser user agent
    - signed_at: Timestamp of signature
    - signature_type: digital (electronic pad), typed, or upload
    - signer_name: Name of person signing
    - signer_title: Title/role of signer
    - consent_checked: Whether signer confirmed understanding
    - witness_user: Optional FK to witness (another user)
    - is_valid: Whether signature passed validation
    - metadata: JSON field for additional signature data
    """

    SIGNATURE_TYPES = [
        ('digital_pad', 'Digital Pad'),
        ('typed', 'Typed Name'),
        ('upload', 'Uploaded Image'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_id = models.IntegerField()  # FK to onboarding_document (avoid circular imports)
    user = models.ForeignKey('User', on_delete=models.PROTECT, related_name='signatures')

    signature_image = models.TextField(help_text="Base64-encoded signature image")
    signature_type = models.CharField(max_length=20, choices=SIGNATURE_TYPES, default='digital_pad')

    signer_name = models.CharField(max_length=255)
    signer_title = models.CharField(max_length=255, blank=True, null=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    signed_at = models.DateTimeField(auto_now_add=True)
    consent_checked = models.BooleanField(default=False)
    is_valid = models.BooleanField(default=True)

    witness_user = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='witnessed_signatures'
    )
    witness_signed_at = models.DateTimeField(null=True, blank=True)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-signed_at']
        indexes = [
            models.Index(fields=['user', 'signed_at']),
            models.Index(fields=['document_id', 'signed_at']),
        ]

    def __str__(self):
        return f"{self.signer_name} - {self.signed_at.strftime('%Y-%m-%d %H:%M')}"

    def get_signature_url(self):
        """Return data URL for displaying signature."""
        if self.signature_image.startswith('data:'):
            return self.signature_image
        return f"data:image/png;base64,{self.signature_image}"


class SignatureField(models.Model):
    """
    Defines signature field requirements on a document.

    Used to mark where signatures must go, what role must sign, etc.
    """

    FIELD_TYPES = [
        ('signature', 'Signature'),
        ('initial', 'Initial'),
        ('date', 'Date'),
        ('checkbox', 'Checkbox'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_id = models.IntegerField()  # FK to onboarding_document

    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, default='signature')
    page_number = models.IntegerField(default=1)

    x_position = models.FloatField(help_text="X coordinate (0-100%)")
    y_position = models.FloatField(help_text="Y coordinate (0-100%)")
    width = models.FloatField(default=30, help_text="Width in percentage")
    height = models.FloatField(default=15, help_text="Height in percentage")

    required_role = models.CharField(max_length=50, blank=True, help_text="Role required to sign")
    optional = models.BooleanField(default=False)

    signed = models.BooleanField(default=False)
    signature = models.ForeignKey(
        DocumentSignature,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['page_number', 'y_position', 'x_position']
        indexes = [
            models.Index(fields=['document_id', 'page_number']),
        ]

    def __str__(self):
        return f"{self.get_field_type_display()} - Page {self.page_number}"
