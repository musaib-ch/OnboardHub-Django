"""Send onboarding reminder notifications. Schedule daily (cron / Task Scheduler):

    python manage.py run_reminders
"""
from django.core.management.base import BaseCommand

from core.automation import run_reminders


class Command(BaseCommand):
    help = "Evaluate reminder rules and notify employees stuck in a stage."

    def handle(self, *args, **opts):
        sent = run_reminders()
        self.stdout.write(self.style.SUCCESS(f"Reminders sent: {sent}"))
