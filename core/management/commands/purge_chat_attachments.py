"""
Management command: purge expired chat attachments.

Run manually:  python manage.py purge_chat_attachments
Schedule via cron or Windows Task Scheduler for nightly execution.
"""
from django.core.management.base import BaseCommand
from core.services.chat_service import purge_expired_attachments, get_attachment_retention_days


class Command(BaseCommand):
    help = "Delete chat attachment files older than the configured retention period."

    def handle(self, *args, **options):
        days = get_attachment_retention_days()
        self.stdout.write(f"Purging attachments older than {days} days...")
        count = purge_expired_attachments()
        self.stdout.write(self.style.SUCCESS(f"Done. {count} attachment(s) deleted."))
