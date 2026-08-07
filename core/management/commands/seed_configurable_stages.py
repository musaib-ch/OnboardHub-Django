"""
Initialize the configurable stage system with default stages and templates.

Usage: python manage.py seed_configurable_stages
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import StageDefinition, StageTemplate, EmployeeStagePath, User, AppSetting


class Command(BaseCommand):
    help = "Seed StageDefinition and StageTemplate with defaults"

    def handle(self, *args, **options):
        self.stdout.write("Seeding configurable stage system...")

        with transaction.atomic():
            # 1. Create stage definitions
            self._create_stages()

            # 2. Create templates
            self._create_templates()

            # 3. Create stage paths for existing employees
            self._create_employee_stage_paths()

            # 4. Set default template
            AppSetting.set('default_stage_template', 'Standard Onboarding')

        self.stdout.write(self.style.SUCCESS("[OK] Seeding complete!"))

    def _create_stages(self):
        """Create default stage definitions."""
        stages_data = [
            {
                "stage_key": "offer",
                "label": "Offer Acceptance",
                "description": "Employee reviews and accepts offer letter",
                "is_mandatory": True,
                "order": 0,
                "default_due_date_days": 7,
                "approval_role": "admin",
                "stage_type": "mandatory",
            },
            {
                "stage_key": "medical",
                "label": "Medical Clearance",
                "description": "Medical review and clearance",
                "is_mandatory": True,
                "order": 1,
                "default_due_date_days": 7,
                "approval_role": "medical_approver",
                "stage_type": "mandatory",
            },
            {
                "stage_key": "pre_onboarding",
                "label": "Pre-Onboarding",
                "description": "Pre-onboarding documents and forms",
                "is_mandatory": True,
                "order": 2,
                "default_due_date_days": 7,
                "approval_role": "admin",
                "stage_type": "mandatory",
            },
            {
                "stage_key": "onboarding",
                "label": "Onboarding",
                "description": "Main onboarding tasks and documents",
                "is_mandatory": True,
                "order": 3,
                "default_due_date_days": 14,
                "approval_role": "admin",
                "stage_type": "mandatory",
            },
            {
                "stage_key": "post_onboarding",
                "label": "Post-Onboarding",
                "description": "Post-onboarding completion",
                "is_mandatory": True,
                "order": 4,
                "default_due_date_days": 30,
                "approval_role": "admin",
                "stage_type": "mandatory",
            },
            {
                "stage_key": "orientation",
                "label": "Orientation",
                "description": "Orientation and welcome session",
                "is_mandatory": False,
                "order": 5,
                "default_due_date_days": 7,
                "approval_role": "admin",
                "stage_type": "optional",
            },
            {
                "stage_key": "training",
                "label": "Training",
                "description": "Role-specific training modules",
                "is_mandatory": False,
                "order": 6,
                "default_due_date_days": 14,
                "approval_role": "admin",
                "stage_type": "optional",
            },
            {
                "stage_key": "onboarding_30_60_90",
                "label": "30/60/90 Day Plan",
                "description": "30/60/90 day milestone planning",
                "is_mandatory": False,
                "order": 7,
                "default_due_date_days": 90,
                "approval_role": "admin",
                "stage_type": "optional",
            },
        ]

        for stage_data in stages_data:
            stage, created = StageDefinition.objects.update_or_create(
                stage_key=stage_data["stage_key"],
                defaults=stage_data
            )
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: {stage.label}")

    def _create_templates(self):
        """Create default stage templates."""
        templates_data = [
            {
                "name": "Standard Onboarding",
                "description": "Full onboarding with all mandatory and optional stages",
                "stages": [
                    "offer_acceptance",
                    "medical",
                    "pre_onboarding",
                    "onboarding",
                    "post_onboarding",
                    "orientation",
                    "training",
                    "onboarding_30_60_90",
                ],
                "is_global": True,
                "is_active": True,
            },
            {
                "name": "Medical + Onboarding",
                "description": "Quick path: Medical clearance then onboarding only",
                "stages": [
                    "medical",
                    "onboarding",
                ],
                "is_global": True,
                "is_active": True,
            },
            {
                "name": "Offer + Medical + Onboarding",
                "description": "Full path: Offer acceptance, medical, then onboarding",
                "stages": [
                    "offer_acceptance",
                    "medical",
                    "onboarding",
                ],
                "is_global": True,
                "is_active": True,
            },
            {
                "name": "Quick Hire",
                "description": "Minimal path: Medical and onboarding only, no pre/post",
                "stages": [
                    "medical",
                    "onboarding",
                    "post_onboarding",
                ],
                "is_global": True,
                "is_active": True,
            },
        ]

        for template_data in templates_data:
            template, created = StageTemplate.objects.update_or_create(
                name=template_data["name"],
                defaults={k: v for k, v in template_data.items() if k != "name"}
            )
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: {template.name}")

    def _create_employee_stage_paths(self):
        """Create stage paths for existing employees (backward compatibility)."""
        employees = User.objects.filter(role="employee")

        # Use the full Standard Onboarding template stages
        default_stages = [
            "offer_acceptance",
            "medical",
            "pre_onboarding",
            "onboarding",
            "post_onboarding",
            "orientation",
            "training",
            "onboarding_30_60_90",
        ]

        created_count = 0
        updated_count = 0
        for emp in employees:
            path, created = EmployeeStagePath.objects.update_or_create(
                employee=emp,
                defaults={
                    "stages": default_stages,
                    "change_reason": "Auto-created during migration to configurable stages",
                }
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        if created_count > 0:
            self.stdout.write(f"  Created {created_count} stage paths for existing employees")
        if updated_count > 0:
            self.stdout.write(f"  Updated {updated_count} stage paths for existing employees")
        if created_count == 0 and updated_count == 0:
            self.stdout.write("  No employees to process")
