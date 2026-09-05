"""
Management command to dispatch pending reminders.

Run via: python manage.py send_reminders
Or via Celery beat scheduler for automation.
"""
from django.core.management.base import BaseCommand
from core.models import Reminder
from core.services.reminder_service import send_reminder, get_pending_reminders_for_dispatch


class Command(BaseCommand):
    help = 'Send pending reminders to employees'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Maximum number of reminders to send in this run (default: 100)',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        pending = get_pending_reminders_for_dispatch()[:limit]

        if not pending:
            self.stdout.write(self.style.SUCCESS('No pending reminders to send'))
            return

        sent_count = 0
        failed_count = 0

        for reminder in pending:
            try:
                if send_reminder(reminder):
                    sent_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'[OK] Sent reminder to {reminder.employee.full_name} '
                            f'({reminder.get_reminder_type_display()})'
                        )
                    )
                else:
                    failed_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f'[FAIL] {reminder.employee.full_name} - {reminder.error_message}'
                        )
                    )
            except Exception as e:
                failed_count += 1
                self.stdout.write(
                    self.style.ERROR(f'[ERROR] {reminder.employee.full_name}: {str(e)}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary: {sent_count} sent, {failed_count} failed out of {len(pending)} total'
            )
        )
