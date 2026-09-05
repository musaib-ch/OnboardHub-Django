"""
Live session views (Phase 3 - JSON consolidated).

Handles: session creation, approvals, registration, attendance.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages
from django.db.models import Q

from ..models import Content, Engagement, User
from ..services import session_service
from ..services.email_triggers import send_session_invitation
from ..decorators import permission_required


@login_required
def sessions_dashboard(request):
    """List all live sessions with role-based filtering."""
    user = request.user

    # Get all sessions and convert to list
    sessions = list(session_service.list_sessions())

    # Filter by role
    if user.role == 'employee':
        sessions = [s for s in sessions if s.meta.get('status') in ['approved', 'scheduled', 'in_progress', 'completed']]

    # Filter by type
    session_type = request.GET.get('type')
    if session_type:
        sessions = [s for s in sessions if s.meta.get('session_type') == session_type]

    # Filter by status
    status = request.GET.get('status')
    if status:
        sessions = [s for s in sessions if s.meta.get('status') == status]

    # Sort by scheduled date (descending)
    sessions.sort(key=lambda s: s.meta.get('scheduled_date', ''), reverse=True)

    # Get user's registrations
    my_sessions = set()
    if user.role == 'employee':
        registrations = Engagement.objects.filter(kind='session', user=user).values_list('content_id', flat=True)
        my_sessions = set(registrations)

    # Pending approvals
    pending_attendee_approvals = []
    if user.role in ['manager', 'hrbp']:
        pending = Engagement.objects.filter(
            kind='session',
            data__attendees__status='pending_approval'
        ).select_related('content', 'user')
        for eng in pending:
            for att in eng.data.get('attendees', []):
                if att.get('status') == 'pending_approval':
                    pending_attendee_approvals.append({
                        'attendee': eng.user,
                        'session': eng.content,
                        'engagement': eng,
                    })

    ctx = {
        'sessions': sessions,
        'my_sessions': my_sessions,
        'pending_approvals': pending_attendee_approvals,
        'session_types': [
            ('orientation', 'Orientation'),
            ('30_day_review', '30-Day Review'),
            ('60_day_review', '60-Day Review'),
            ('90_day_review', '90-Day Review'),
            ('training', 'Training'),
            ('meeting', 'General Meeting'),
        ],
        'current_type': session_type,
        'current_status': status,
    }

    return render(request, 'sessions/dashboard.html', ctx)


@login_required
def create_session(request):
    """Create a new live session."""
    if not request.user.has_perm_key('create_live_sessions'):
        return render(request, '403.html', status=403)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        session_type = request.POST.get('session_type', 'orientation')
        scheduled_date_str = request.POST.get('scheduled_date')
        duration = int(request.POST.get('duration_minutes', 60))
        use_zoom = request.POST.get('use_zoom') == 'on'

        if not title or not scheduled_date_str:
            messages.error(request, 'Title and date are required.')
            return render(request, 'sessions/create_session.html')

        # Parse datetime
        try:
            scheduled_date = timezone.make_aware(timezone.datetime.fromisoformat(scheduled_date_str))
        except ValueError:
            messages.error(request, 'Invalid date/time format.')
            return render(request, 'sessions/create_session.html')

        # Create session
        try:
            session = session_service.create_session(
                title=title,
                description=description,
                session_type=session_type,
                scheduled_date=scheduled_date,
                duration_minutes=duration,
                created_by=request.user,
                use_zoom=use_zoom,
            )

            # Send invitation emails to session attendees if approved
            if not request.user.role == 'employee':
                # Get attendees from session
                attendees = session_service.get_session_attendees(session)
                attendee_users = [User.objects.get(id=a['user_id']) for a in attendees if a.get('user_id')]
                send_session_invitation(session, attendee_users)

            if request.user.role == 'employee':
                messages.success(request, 'Session created! Waiting for HRBP approval.')
            else:
                messages.success(request, 'Session created and approved!')

            return redirect('session_detail', session_id=session.id)
        except Exception as e:
            messages.error(request, f'Error creating session: {str(e)}')

    ctx = {
        'session_types': [
            ('orientation', 'Orientation'),
            ('30_day_review', '30-Day Review'),
            ('60_day_review', '60-Day Review'),
            ('90_day_review', '90-Day Review'),
            ('training', 'Training'),
        ],
    }

    return render(request, 'sessions/create_session.html', ctx)


@login_required
def session_detail(request, session_id):
    """View session details and attendees."""
    session = get_object_or_404(Content, id=session_id, kind='live_session')
    session_data = session.meta

    attendees = session_service.get_session_attendees(session)

    my_registration = None
    for att in attendees:
        if att.get('user_id') == request.user.id:
            my_registration = att
            break

    is_creator = session.created_by_id == request.user.id
    is_organizer = request.user.has_perm_key('manage_live_sessions')
    can_manage = is_organizer or is_creator

    # Attendance stats
    attended_count = sum(1 for a in attendees if a.get('status') == 'attended')
    total = len(attendees)
    attendance_rate = round(attended_count / total * 100) if total > 0 else 0

    # Feedback
    feedback_list = session_service.get_session_feedback(session)
    all_ratings = [f['rating'] for f in feedback_list if f.get('rating')]
    avg_rating = round(sum(all_ratings) / len(all_ratings), 1) if all_ratings else None

    # Did current user already submit feedback?
    my_feedback = next(
        (f for f in feedback_list if f['user'].id == request.user.id), None
    )

    ctx = {
        'session': session,
        'session_data': session_data,
        'attendees': attendees,
        'my_registration': my_registration,
        'is_creator': is_creator,
        'is_organizer': is_organizer,
        'can_manage': can_manage,
        'attended_count': attended_count,
        'attendance_rate': attendance_rate,
        'feedback_list': feedback_list,
        'avg_rating': avg_rating,
        'my_feedback': my_feedback,
    }

    return render(request, 'sessions/session_detail.html', ctx)


@login_required
@require_http_methods(['POST'])
def register_session(request, session_id):
    """Register for a session."""
    session = get_object_or_404(Content, id=session_id, kind='live_session')

    # Check if already registered
    existing = Engagement.objects.filter(kind='session', user=request.user, content=session).first()
    if existing:
        messages.info(request, 'You are already registered for this session.')
        return redirect('session_detail', session_id=session.id)

    # Determine if needs approval
    needs_approval = session.meta.get('session_type') in ['orientation', '30_day_review', '60_day_review', '90_day_review']
    status = 'pending_approval' if needs_approval else 'approved'

    session_service.add_attendee(session, request.user, status=status)

    if needs_approval:
        messages.success(request, 'Registration submitted! Waiting for manager approval.')
    else:
        messages.success(request, 'You are registered for this session!')

    return redirect('session_detail', session_id=session.id)


@login_required
@require_http_methods(['POST'])
@permission_required('manage_live_sessions')
def approve_attendee(request, session_id, attendee_id):
    """Manager/HRBP approves attendee registration."""
    session = get_object_or_404(Content, id=session_id, kind='live_session')
    attendee = get_object_or_404(User, id=attendee_id)

    session_service.approve_attendee(session, attendee, request.user)

    messages.success(request, f'{attendee.full_name} approved!')
    return redirect('session_detail', session_id=session.id)


@login_required
@require_http_methods(['POST'])
@permission_required('manage_live_sessions')
def approve_session(request, session_id):
    """HRBP approves employee-created session."""
    session = get_object_or_404(Content, id=session_id, kind='live_session')

    if session.meta.get('status') != 'pending_approval':
        messages.error(request, 'Session is not pending approval.')
        return redirect('session_detail', session_id=session.id)

    session_service.approve_session(session, request.user)

    messages.success(request, 'Session approved!')
    return redirect('session_detail', session_id=session.id)


@login_required
@require_http_methods(['POST'])
@permission_required('manage_live_sessions')
def mark_attendance(request, session_id):
    """Admin/HRBP marks selected attendees as attended."""
    session = get_object_or_404(Content, id=session_id, kind='live_session')
    attendee_ids = request.POST.getlist('attendee_ids')

    if not attendee_ids:
        messages.warning(request, 'No attendees selected.')
        return redirect('session_detail', session_id=session.id)

    marked = session_service.mark_attendance_bulk(session, attendee_ids, request.user)
    messages.success(request, f'{len(marked)} attendee(s) marked as attended.')
    return redirect('session_detail', session_id=session.id)


@login_required
@require_http_methods(['POST'])
def session_feedback(request, session_id):
    """Employee submits star rating + comment after attending session."""
    session = get_object_or_404(Content, id=session_id, kind='live_session')

    # Must have attended
    engagement = Engagement.objects.filter(kind='session', user=request.user, content=session).first()
    if not engagement:
        messages.error(request, 'You are not registered for this session.')
        return redirect('session_detail', session_id=session.id)

    attended = any(
        att.get('status') == 'attended' and att.get('user_id') == request.user.id
        for att in engagement.data.get('attendees', [])
    )
    if not attended:
        messages.error(request, 'Feedback is only available after you have attended.')
        return redirect('session_detail', session_id=session.id)

    rating = request.POST.get('rating', 0)
    comment = request.POST.get('comment', '').strip()

    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError()
    except (ValueError, TypeError):
        messages.error(request, 'Please select a rating from 1 to 5.')
        return redirect('session_detail', session_id=session.id)

    session_service.add_session_feedback(session, request.user, rating, comment)
    messages.success(request, 'Thank you for your feedback!')
    return redirect('session_detail', session_id=session.id)
