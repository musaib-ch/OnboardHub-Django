from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    Tenant, User, OrgUnit, AppSetting, Form, FormResponse, OnboardingDocument,
    MedicalRecord, Notification, AuditLog, Content, Engagement, ReviewMessage,
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


admin.site.register([
    Tenant, OrgUnit, AppSetting, Form, FormResponse, OnboardingDocument,
    MedicalRecord, Notification, AuditLog, Content, Engagement, ReviewMessage,
])
