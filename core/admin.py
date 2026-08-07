from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    Tenant, User, OrgUnit, AppSetting, Form, FormResponse, OnboardingDocument,
    MedicalRecord, Notification, AuditLog, Content, Engagement, ReviewMessage,
    # Offer-related models
    OfferFieldDefinition, OfferTemplate, OfferEmailTemplate, Offer, OfferFieldValue,
    OfferAttachment, OfferStatusHistory, OfferApproval, OfferSignature, OfferSendToken,
    OfferExport, OfferAuditLog, OfferVisibility,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "role", "status", "is_active")
    list_filter = ("role", "status", "is_active")
    search_fields = ("email", "full_name", "employee_id")
    filter_horizontal = ()
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "phone_number", "avatar", "department",
                                "position_title", "employee_id")}),
        ("Role & status", {"fields": ("role", "status", "employee_type", "tenant",
                                      "must_change_password")}),
        ("Stage Timing", {"fields": ("stage_entered_at", "stage_due_date", "stage_due_date_override"),
                          "description": "Auto-calculated due dates based on Stage configuration. HR can override per-employee."}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",),
                "fields": ("email", "full_name", "role", "password1", "password2")}),
    )


from django.utils.html import format_html


class OfferTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'created_by', 'is_default', 'updated_at')
    search_fields = ('name', 'description')
    list_filter = ('is_default',)

    class Media:
        js = [
            'https://cdn.tiny.cloud/1/no-api-key/tinymce/6/tinymce.min.js',
            '/static/js/offer_tinymce_init.js',
        ]


admin.site.register([
    Tenant, OrgUnit, AppSetting, Form, FormResponse, OnboardingDocument,
    MedicalRecord, Notification, AuditLog, Content, Engagement, ReviewMessage,
    # Offer models (register OfferTemplate with custom admin)
    OfferFieldDefinition, Offer, OfferFieldValue,
    OfferAttachment, OfferStatusHistory, OfferApproval, OfferSignature, OfferSendToken,
    OfferExport, OfferAuditLog, OfferVisibility,
])

admin.site.register(OfferTemplate, OfferTemplateAdmin)
admin.site.register(OfferEmailTemplate)
