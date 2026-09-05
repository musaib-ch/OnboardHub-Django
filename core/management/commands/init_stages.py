"""
Management command to initialize default onboarding stages.

Usage: python manage.py init_stages
"""
from django.core.management.base import BaseCommand
from core.models import StageDefinition


class Command(BaseCommand):
    help = "Initialize default onboarding stages with due dates"

    def handle(self, *args, **options):
        self.stdout.write("Initializing onboarding stages...")

        stages_created = 0
        stages = [
            {
                "stage_key": "medical",
                "label": "Medical Clearance",
                "default_due_date_days": 7,
                "order": 0,
            },
            {
                "stage_key": "pre_onboarding",
                "label": "Pre-Onboarding",
                "default_due_date_days": 7,
                "order": 1,
            },
            {
                "stage_key": "onboarding",
                "label": "Onboarding",
                "default_due_date_days": 14,
                "order": 2,
            },
            {
                "stage_key": "post_onboarding",
                "label": "Post-Onboarding",
                "default_due_date_days": 7,
                "order": 3,
            },
        ]

        for stage_data in stages:
            stage, created = StageDefinition.objects.get_or_create(
                stage_key=stage_data["stage_key"],
                defaults=stage_data
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[+] Created stage: {stage.label} ({stage.default_due_date_days}d)"
                    )
                )
                stages_created += 1
            else:
                self.stdout.write(f"[*] Stage already exists: {stage.label}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n[OK] Done! {stages_created} new stages created."
            )
        )
