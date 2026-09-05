"""Training deadline nudges, manager escalation, and recertification resets.

Schedule daily (cron / Windows Task Scheduler), alongside run_reminders:

    python manage.py training_reminders
"""
from django.core.management.base import BaseCommand

from core.views.training_views import run_training_reminders


class Command(BaseCommand):
    help = "Nudge due/overdue training, escalate overdue to admins, reset recurring paths."

    def handle(self, *args, **opts):
        c = run_training_reminders()
        self.stdout.write(self.style.SUCCESS(
            f"Training reminders — due_soon: {c['due_soon']}, overdue: {c['overdue']}, "
            f"escalated: {c['escalated']}, recurred: {c['recurred']}"
        ))
