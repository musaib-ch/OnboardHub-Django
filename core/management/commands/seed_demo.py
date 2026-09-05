"""Bootstrap a usable demo: tenant, super admin, departments, forms, a demo employee.

Usage:
    python manage.py seed_demo
    python manage.py seed_demo --admin-email you@company.com --admin-password Secret123
"""
import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    Tenant, User, OrgUnit, AppSetting, Form, OnboardingDocument, MedicalRecord,
    Content, Engagement,
)


class Command(BaseCommand):
    help = "Seed demo data (tenant, super admin, departments, forms, employee)."

    def add_arguments(self, parser):
        parser.add_argument("--admin-email", default="admin@onboardhub.local")
        parser.add_argument("--admin-password", default="qwerty1234")
        parser.add_argument("--employee-email", default="employee@onboardhub.local")
        parser.add_argument("--employee-password", default="qwerty1234")

    def handle(self, *args, **opts):
        tenant, _ = Tenant.objects.get_or_create(
            name="Demo Company", defaults={"subdomain": "demo"}
        )

        # Theme defaults (so site_settings render nicely)
        for key, val in {
            "site_title": "OnboardHub",
            "primary_color": "#1d2b4f",
            "accent_color": "#324b8a",
            "sidebar_bg": "#1d2b4f",
        }.items():
            AppSetting.objects.get_or_create(key=key, defaults={"value": val})

        # Departments
        depts = {}
        for name in ["Engineering", "Human Resources", "Finance", "Operations"]:
            d, _ = OrgUnit.objects.get_or_create(
                kind="department", name=name, tenant=tenant
            )
            depts[name] = d

        # Other organization dropdown options (grades, locations, payroll, types)
        org_seed = {
            "grade": ["G1", "G2", "G3", "M1", "M2", "Executive"],
            "location": ["Head Office", "Karachi", "Lahore", "Islamabad", "Remote"],
            "payroll": ["Monthly", "Contract", "Hourly"],
            "employee_type": ["Permanent", "Contractual", "Trainee", "Intern"],
            "designation": ["Officer", "Senior Officer", "Manager", "Senior Manager"],
        }
        for kind, names in org_seed.items():
            for name in names:
                OrgUnit.objects.get_or_create(kind=kind, name=name, tenant=tenant)

        # Super admin
        admin, created = User.objects.get_or_create(
            email=opts["admin_email"].lower(),
            defaults={
                "full_name": "System Administrator",
                "role": "super_admin",
                "status": "completed",
                "is_staff": True,
                "is_superuser": True,
                "must_change_password": False,
                "tenant": tenant,
            },
        )
        admin.set_password(opts["admin_password"])
        admin.is_staff = True
        admin.is_superuser = True
        admin.must_change_password = False
        admin.save()

        # Demo employee in pre-onboarding
        emp, _ = User.objects.get_or_create(
            email=opts["employee_email"].lower(),
            defaults={
                "full_name": "Demo Employee",
                "role": "employee",
                "status": "medical_upload",
                "must_change_password": False,
                "tenant": tenant,
                "department": depts["Engineering"],
                "employee_id": "EMP-0001",
                "position_title": "Software Engineer",
                "date_of_joining": timezone.now().date(),
                "has_seen_welcome": True,
            },
        )
        emp.set_password(opts["employee_password"])
        emp.must_change_password = False
        emp.save()

        # Sample pre-onboarding form
        if not Form.objects.filter(stage="pre_onboarding").exists():
            Form.objects.create(
                tenant=tenant,
                name="Personal Information",
                description="Basic details we need before your first day.",
                stage="pre_onboarding",
                is_active=True,
                display_order=1,
                schema={
                    "sections": [
                        {
                            "title": "Personal Details",
                            "description": "Tell us about yourself.",
                            "fields": [
                                {"label": "Full Legal Name", "field_name": "legal_name",
                                 "field_type": "text", "is_required": True,
                                 "placeholder": "As on your CNIC", "options": []},
                                {"label": "Date of Birth", "field_name": "dob",
                                 "field_type": "date", "is_required": True, "options": []},
                                {"label": "CNIC", "field_name": "cnic",
                                 "field_type": "text", "is_required": True,
                                 "placeholder": "12345-1234567-1", "options": []},
                                {"label": "Personal Email", "field_name": "personal_email",
                                 "field_type": "email", "is_required": False, "options": []},
                                {"label": "Shirt Size", "field_name": "shirt_size",
                                 "field_type": "dropdown", "is_required": False,
                                 "options": ["S", "M", "L", "XL"]},
                            ],
                        },
                        {
                            "title": "Emergency Contact",
                            "fields": [
                                {"label": "Contact Name", "field_name": "ec_name",
                                 "field_type": "text", "is_required": True, "options": []},
                                {"label": "Contact Phone", "field_name": "ec_phone",
                                 "field_type": "phone", "is_required": True, "options": []},
                            ],
                        },
                    ]
                },
            )

        # Sample onboarding document
        OnboardingDocument.objects.get_or_create(
            title="Code of Conduct",
            stage="onboarding",
            defaults={
                "tenant": tenant,
                "description": "Please read and sign our code of conduct.",
                "body": "<p>Welcome! By signing you agree to our code of conduct.</p>",
                "is_required": True,
            },
        )

        # Medical requirement catalog entry
        MedicalRecord.objects.get_or_create(
            requirement_name="Pre-employment Medical Check",
            is_catalog=True,
            defaults={"tenant": tenant, "is_required": True,
                      "description": "Upload your medical fitness certificate."},
        )

        # ── Training modules + a learning path, assigned to the demo employee ──
        module_specs = [
            ("Welcome & Company Values", "Orientation",
             "<p>An introduction to who we are and what we stand for.</p>"),
            ("Information Security Basics", "Compliance",
             "<p>Core security practices every employee must follow.</p>"),
            ("Workplace Health & Safety", "Compliance",
             "<p>Stay safe: emergency procedures and reporting.</p>"),
        ]
        modules = []
        for title, category, body in module_specs:
            m, _ = Content.objects.get_or_create(
                kind="training", title=title, tenant=tenant,
                defaults={"category": category, "body": body, "is_active": True,
                          "created_by": admin},
            )
            modules.append(m)

        path, _ = Content.objects.get_or_create(
            kind="learning_path", title="New Hire Essentials", tenant=tenant,
            defaults={"category": "Onboarding", "created_by": admin,
                      "body": "Everything a new hire should complete in week one."},
        )
        path.meta = {
            "modules": [{"content_id": m.id, "required": True} for m in modules],
            "due_days": 14, "recurrence_days": 0,
        }
        path.save()

        if not Engagement.objects.filter(user=emp, kind="enrollment", content=path).exists():
            Engagement.objects.create(
                kind="enrollment", user=emp, content=path, tenant=tenant,
                title=path.title, status="assigned", progress=0,
                due_date=timezone.now().date() + datetime.timedelta(days=14),
                data={"assigned_by": admin.id, "assigned_at": timezone.now().isoformat()},
            )

        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
        self.stdout.write(f"  Admin:    {opts['admin_email']} / {opts['admin_password']}")
        self.stdout.write(f"  Employee: {opts['employee_email']} / {opts['employee_password']}")
