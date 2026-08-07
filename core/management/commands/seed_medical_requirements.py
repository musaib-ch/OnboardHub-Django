"""Seed the medical requirement catalog (mirrors the original Flask build).

Each catalog entry becomes a *separate* upload + review row for every employee
when they reach the medical stage.

    python manage.py seed_medical_requirements
"""
from django.core.management.base import BaseCommand

from core.models import MedicalRecord, Tenant


# (name, min_age, max_age, gender, note)
# The Django model stores applicability rules in `meta`, so we translate the
# Flask-style seed into the closest equivalent representation here.
REQUIREMENTS = [
    ("CBC", 0, None, "all", ""),
    ("ESR", 0, None, "all", ""),
    ("LFTs", 0, None, "all", ""),
    ("RFTs (eGFR included)", 0, None, "all", ""),
    ("HbA1C", 0, None, "all", ""),
    ("Lipid Profile (Fasting)", 0, None, "all", ""),
    ("HBsAg", 0, None, "all", ""),
    ("Anti HCV", 0, None, "all", ""),
    ("Urine C/E", 0, None, "all", ""),
    ("X-Ray Chest (with Radiologist Report)", 0, None, "all", ""),
    ("Serum Electrolytes", 0, None, "all", ""),
    ("Uric Acid", 0, None, "all", ""),
    ("Serum Calcium", 0, None, "all", ""),
    ("Fitness Certificate by Consultant", 0, None, "all", ""),
    ("PSA", 40, None, "male", "Prostate-specific antigen."),
    ("CA-125", 40, None, "female", "Ovarian cancer marker."),
]


class Command(BaseCommand):
    help = "Seed the medical requirement catalog (with age/gender applicability)."

    def handle(self, *args, **opts):
        tenant = Tenant.objects.first()
        created = 0
        for name, min_age, max_age, gender, note in REQUIREMENTS:
            meta = {
                "min_age": min_age,
                "max_age": max_age,
                "mandatory": True,
                "is_active": True,
            }
            if gender != "all":
                meta["gender"] = gender
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
