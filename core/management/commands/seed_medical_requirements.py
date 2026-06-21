"""Seed the medical requirement catalog (mirrors the original Flask build).

Each catalog entry becomes a *separate* upload + review row for every employee
when they reach the medical stage.

    python manage.py seed_medical_requirements
"""
from django.core.management.base import BaseCommand

from core.models import MedicalRecord, Tenant


# (name, description, applicability-rule meta)
# meta {} = applies to everyone (required). {"gender","min_age"} = conditional.
REQUIREMENTS = [
    ("CBC", "", {}),
    ("ESR", "", {}),
    ("LFTs", "", {}),
    ("RFTs (eGFR included)", "", {}),
    ("HbA1C", "", {}),
    ("Lipid Profile (Fasting)", "", {}),
    ("HBsAg", "", {}),
    ("Anti HCV", "", {}),
    ("Urine C/E", "", {}),
    ("X-Ray Chest (with Radiologist Report)", "", {}),
    ("Serum Electrolytes", "", {}),
    ("Uric Acid", "", {}),
    ("Serum Calcium", "", {}),
    ("Fitness Certificate by Consultant", "", {}),
    ("PSA", "Prostate-specific antigen.", {"gender": "male", "min_age": 40}),
    ("CA-125", "Ovarian cancer marker.", {"gender": "female", "min_age": 40}),
]


class Command(BaseCommand):
    help = "Seed the medical requirement catalog (with age/gender applicability)."

    def handle(self, *args, **opts):
        tenant = Tenant.objects.first()
        created = 0
        for name, note, meta in REQUIREMENTS:
            row, was_created = MedicalRecord.objects.get_or_create(
                requirement_name=name, is_catalog=True,
                defaults={"tenant": tenant, "is_required": True,
                          "description": note, "meta": meta},
            )
            # Keep applicability rules current on re-runs.
            if not was_created and row.meta != meta:
                row.meta = meta
                row.description = note or row.description
                row.save(update_fields=["meta", "description"])
            created += int(was_created)
        total = MedicalRecord.objects.filter(is_catalog=True).count()
        self.stdout.write(self.style.SUCCESS(
            f"Medical catalog seeded ({created} new, {total} total requirements)."
        ))
