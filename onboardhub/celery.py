"""
Celery configuration for async task processing.

Handles background email sending, reminders, and scheduled tasks.
"""
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'onboardhub.settings')

app = Celery('onboardhub')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Scheduled tasks (beat schedule)
app.conf.beat_schedule = {
    # Send session reminders 24 hours before
    'send-session-reminders-24h': {
        'task': 'core.tasks.send_session_reminders_24h',
        'schedule': crontab(hour=9, minute=0),  # Every day at 9 AM
    },
    # Send session reminders 7 days before
    'send-session-reminders-7d': {
        'task': 'core.tasks.send_session_reminders_7d',
        'schedule': crontab(hour=8, minute=0),  # Every day at 8 AM
    },
    # Send stage deadline reminders
    'send-stage-reminders': {
        'task': 'core.tasks.send_stage_deadline_reminders',
        'schedule': crontab(hour=10, minute=0),  # Every day at 10 AM
    },
    # Send document/form reminders
    'send-document-reminders': {
        'task': 'core.tasks.send_document_reminders',
        'schedule': crontab(hour=11, minute=0),  # Every day at 11 AM
    },
}


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
