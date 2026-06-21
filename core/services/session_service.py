"""
Live session service - JSON-based (no new tables).

Handles: session creation, approvals, attendance, recording.
Session data stored in: Content.meta (kind='live_session')
Attendance tracked in: Engagement.data (kind='session')
"""
from django.utils import timezone
from django.db.models import Q

from ..models import Content, Engagement, User
from .zoom_service import get_zoom_service


def create_session(title, description, session_type, scheduled_date, duration_minutes, created_by, related_content=None, use_zoom=True):
    """
    Create a live session (Content with kind='live_session').

    Returns: Content object
    """
    zoom_data = {}

    # Try to create Zoom meeting (optional)
    if use_zoom:
        zoom_service = get_zoom_service()
        if zoom_service.is_configured():
            meeting = zoom_service.create_meeting(title, scheduled_date, duration_minutes)
            if meeting:
                zoom_data = {
                    'meeting_id': meeting.get('zoom_meeting_id'),
                    'join_url': meeting.get('zoom_join_url'),
                    'start_url': meeting.get('zoom_start_url'),
                    'is_recorded': True,
                }

    # Determine initial status
    status = 'pending_approval' if created_by.role == 'employee' else 'approved'
    approved_by = None if created_by.role == 'employee' else created_by.id
    approved_at = None if created_by.role == 'employee' else timezone.now().isoformat()

    # Create Content record
    session = Content.objects.create(
        kind='live_session',
        title=title,
        body=description,
        created_by=created_by,
        is_active=True,
        meta={
            'session_type': session_type,
            'scheduled_date': scheduled_date.isoformat(),
            'duration_minutes': duration_minutes,
            'timezone': 'UTC',
            'status': status,
            'created_by': created_by.id,
            'approved_by': approved_by,
            'approved_at': approved_at,
            'zoom': zoom_data,
        }
    )

    # Add creator as attendee (auto-approved)
    add_attendee(session, created_by, status='approved')

    return session


def get_session_detail(session_id):
    """Get session metadata."""
    try:
        session = Content.objects.get(id=session_id, kind='live_session')
        return session.meta
    except Content.DoesNotExist:
        return None


def list_sessions(filters=None):
    """
    List sessions with optional filters.

    filters: {type, status, created_by, scheduled_before, scheduled_after}
    """
    sessions = Content.objects.filter(kind='live_session', is_active=True).order_by('-created_at')

    if filters:
        if filters.get('type'):
            sessions = sessions.filter(meta__session_type=filters['type'])
        if filters.get('status'):
            sessions = sessions.filter(meta__status=filters['status'])
        if filters.get('created_by'):
            sessions = sessions.filter(created_by_id=filters['created_by'])

    return sessions


def add_attendee(session, attendee, status='invited', approved_by=None):
    """Add attendee to session."""
    engagement, created = Engagement.objects.get_or_create(
        kind='session',
        user=attendee,
        content=session,
        defaults={
            'title': f'Session: {session.title}',
            'status': 'active',
            'data': {
                'attendees': [{
                    'user_id': attendee.id,
                    'status': status,
                    'approved_by': approved_by.id if approved_by else None,
                    'approved_at': timezone.now().isoformat() if approved_by else None,
                }]
            }
        }
    )

    if not created:
        # Update attendee list
        attendees = engagement.data.get('attendees', [])
        # Check if already added
        for att in attendees:
            if att.get('user_id') == attendee.id:
                att['status'] = status
                att['approved_by'] = approved_by.id if approved_by else att.get('approved_by')
                engagement.data['attendees'] = attendees
                engagement.save()
                return engagement

        attendees.append({
            'user_id': attendee.id,
            'status': status,
            'approved_by': approved_by.id if approved_by else None,
            'approved_at': timezone.now().isoformat() if approved_by else None,
        })
        engagement.data['attendees'] = attendees
        engagement.save()

    return engagement


def approve_attendee(session, attendee, approved_by):
    """Approve attendee registration."""
    try:
        engagement = Engagement.objects.get(kind='session', user=attendee, content=session)
        attendees = engagement.data.get('attendees', [])

        for att in attendees:
            if att.get('user_id') == attendee.id:
                att['status'] = 'approved'
                att['approved_by'] = approved_by.id
                att['approved_at'] = timezone.now().isoformat()

        engagement.data['attendees'] = attendees
        engagement.save()
        return True
    except Engagement.DoesNotExist:
        return False


def approve_session(session, approved_by):
    """Approve a pending session."""
    session.meta['status'] = 'approved'
    session.meta['approved_by'] = approved_by.id
    session.meta['approved_at'] = timezone.now().isoformat()
    session.save()
    return session


def mark_attended(session, attendee, join_time, leave_time):
    """Mark attendee as attended with duration."""
    try:
        engagement = Engagement.objects.get(kind='session', user=attendee, content=session)
        attendees = engagement.data.get('attendees', [])

        for att in attendees:
            if att.get('user_id') == attendee.id:
                att['status'] = 'attended'
                att['joined_at'] = join_time.isoformat() if join_time else None
                att['left_at'] = leave_time.isoformat() if leave_time else None
                if join_time and leave_time:
                    duration = int((leave_time - join_time).total_seconds() / 60)
                    att['duration_minutes'] = duration

        engagement.data['attendees'] = attendees
        engagement.save()
        return True
    except Engagement.DoesNotExist:
        return False


def get_session_attendees(session):
    """Get all attendees for a session."""
    attendances = Engagement.objects.filter(kind='session', content=session).select_related('user')

    attendees = []
    for engagement in attendances:
        for att in engagement.data.get('attendees', []):
            if att.get('user_id') == engagement.user_id:
                attendees.append({
                    **att,
                    'user': engagement.user,
                })

    return attendees


def get_user_session_registrations(user):
    """Get sessions user is registered for."""
    engagements = Engagement.objects.filter(kind='session', user=user).select_related('content')
    return [e.content for e in engagements]


def filter_sessions_for_user(user, all_sessions=None):
    """
    Filter sessions user can view based on role.

    Employee: sees approved/completed sessions
    Manager/HRBP: sees all sessions
    """
    if all_sessions is None:
        all_sessions = list_sessions()

    if user.role == 'employee':
        return [s for s in all_sessions if s.meta.get('status') in ['approved', 'scheduled', 'in_progress', 'completed']]
    else:
        return all_sessions
