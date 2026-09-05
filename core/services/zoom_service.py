"""
Zoom API service - JSON-based configuration (no new tables).

Handles: OAuth tokens, meeting creation, recording management.
Config stored in: AppSetting['zoom_oauth']
Session data stored in: Content.meta (kind='live_session')
"""
import requests
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.core.mail import EmailMessage

from ..models import AppSetting, Content


class ZoomService:
    """Zoom OAuth + API wrapper."""

    BASE_URL = "https://api.zoom.us/v2"
    OAUTH_TOKEN_URL = "https://zoom.us/oauth/token"

    def __init__(self):
        """Load Zoom config from AppSetting."""
        try:
            setting = AppSetting.objects.get(key='zoom_oauth')
            self.config = setting.value or {}
        except AppSetting.DoesNotExist:
            self.config = {}

    def is_configured(self):
        """Check if Zoom is set up."""
        return bool(self.config.get('is_configured'))

    def is_token_valid(self):
        """Check if access token is still valid."""
        if not self.config.get('access_token'):
            return False

        expires_at = self.config.get('token_expires_at')
        if expires_at:
            expiration = timezone.make_aware(timezone.datetime.fromisoformat(expires_at))
            return timezone.now() < expiration

        return False

    def refresh_token_if_needed(self):
        """Auto-refresh if token expired."""
        if not self.is_token_valid():
            return self.refresh_access_token()
        return True

    def refresh_access_token(self):
        """Refresh OAuth token."""
        if not self.config.get('refresh_token'):
            return False

        try:
            auth = (self.config.get('client_id'), self.config.get('client_secret'))
            data = {'grant_type': 'refresh_token', 'refresh_token': self.config.get('refresh_token')}

            response = requests.post(self.OAUTH_TOKEN_URL, auth=auth, data=data, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            self.config['access_token'] = token_data.get('access_token')
            self.config['refresh_token'] = token_data.get('refresh_token', self.config.get('refresh_token'))

            expires_in = token_data.get('expires_in', 3600)
            self.config['token_expires_at'] = (timezone.now() + timedelta(seconds=expires_in)).isoformat()
            self.config['last_sync_at'] = timezone.now().isoformat()
            self.config['last_error'] = None

            # Save to AppSetting
            self._save_config()
            return True
        except Exception as e:
            self.config['last_error'] = str(e)
            self._save_config()
            return False

    def create_meeting(self, title, scheduled_date, duration_minutes=60):
        """Create Zoom meeting."""
        if not self.refresh_token_if_needed():
            return None

        try:
            meeting_data = {
                'topic': title,
                'type': 2,  # Scheduled
                'start_time': scheduled_date.isoformat(),
                'duration': duration_minutes,
                'timezone': self.config.get('timezone', 'UTC'),
                'settings': {
                    'host_video': True,
                    'participant_video': True,
                    'waiting_room': self.config.get('enable_waiting_room', True),
                    'auto_recording': self.config.get('auto_record_type', 'cloud'),
                },
            }

            headers = {'Authorization': f'Bearer {self.config.get("access_token")}', 'Content-Type': 'application/json'}
            response = requests.post(f'{self.BASE_URL}/users/me/meetings', json=meeting_data, headers=headers, timeout=10)
            response.raise_for_status()

            meeting = response.json()
            return {
                'zoom_meeting_id': str(meeting.get('id')),
                'zoom_join_url': meeting.get('join_url'),
                'zoom_start_url': meeting.get('start_url'),
            }
        except Exception as e:
            self.config['last_error'] = str(e)
            self._save_config()
            return None

    def get_meeting(self, meeting_id):
        """Get meeting details."""
        if not self.refresh_token_if_needed():
            return None

        try:
            headers = {'Authorization': f'Bearer {self.config.get("access_token")}'}
            response = requests.get(f'{self.BASE_URL}/meetings/{meeting_id}', headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.config['last_error'] = str(e)
            self._save_config()
            return None

    def get_recordings(self, meeting_id):
        """Get meeting recordings."""
        if not self.refresh_token_if_needed():
            return None

        try:
            headers = {'Authorization': f'Bearer {self.config.get("access_token")}'}
            response = requests.get(f'{self.BASE_URL}/meetings/{meeting_id}/recordings', headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return None

    def _save_config(self):
        """Save config back to AppSetting."""
        try:
            setting, _ = AppSetting.objects.get_or_create(key='zoom_oauth')
            setting.value = self.config
            setting.save()
        except Exception:
            pass

    @staticmethod
    def send_calendar_invite(email, title, join_url, start_time, duration_minutes):
        """Send calendar invite via email."""
        ical_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//OnboardHub//Zoom Integration//EN
BEGIN:VEVENT
UID:{join_url}@onboardhub.com
DTSTAMP:{timezone.now().isoformat()}
DTSTART:{start_time.isoformat()}
DTEND:{(start_time + timedelta(minutes=duration_minutes)).isoformat()}
SUMMARY:{title}
DESCRIPTION:Join Zoom meeting: {join_url}
LOCATION:{join_url}
END:VEVENT
END:VCALENDAR"""

        try:
            email_msg = EmailMessage(
                subject=f"Zoom Meeting: {title}",
                body=f"""You're invited to: {title}

Time: {start_time.strftime('%Y-%m-%d %H:%M %Z')}
Duration: {duration_minutes} minutes

Join URL: {join_url}""",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email],
            )
            email_msg.attach('meeting.ics', ical_content, 'text/calendar')
            email_msg.send()
            return True
        except Exception:
            return False


def get_zoom_service():
    """Get Zoom service instance."""
    return ZoomService()
