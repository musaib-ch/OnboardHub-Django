"""
Analytics service for onboarding metrics and reporting.

Provides metrics on stage completion, time-to-completion, funnel analysis, etc.
"""
from datetime import timedelta
from django.db.models import Q, Count, Avg, F, Case, When, IntegerField
from django.utils import timezone
from .. import pipeline
from ..models import User, Content, Engagement
from ..permissions import role_scope_type


def _get_scoped_employees(viewer):
    """Restrict query to viewer's department/location scope."""
    qs = User.objects.filter(role='employee').exclude(status='deleted')
    if not viewer:
        return qs
    scope_type = role_scope_type(viewer.role)
    if scope_type == "department":
        depts = (viewer.scope or {}).get("departments") or []
        return qs.filter(department_id__in=depts) if depts else qs.none()
    elif scope_type == "location":
        locs = (viewer.scope or {}).get("locations") or []
        return qs.filter(location_code__in=locs) if locs else qs.none()
    return qs


def get_onboarding_funnel(viewer=None):
    """
    Get funnel metrics: how many employees at each stage.

    Returns dict with stage counts and percentages.
    """
    employees = _get_scoped_employees(viewer)
    all_employees = employees.count()

    if not all_employees:
        return {}

    stages = pipeline.enabled_stages()
    funnel = {}

    for stage_key in stages:
        # Count employees who have reached this stage or beyond
        status_list = _statuses_from_stage(stage_key, stages)
        count = employees.filter(status__in=status_list).count()

        percentage = (count / all_employees * 100) if all_employees else 0

        funnel[stage_key] = {
            'label': pipeline.STAGE_LABELS.get(stage_key, stage_key),
            'count': count,
            'percentage': round(percentage, 1),
        }

    return funnel


def get_stage_completion_metrics(viewer=None):
    """
    Get completion metrics for each stage.

    Returns: {stage_key: {completed: N, total: N, rate: %}}
    """
    employees = _get_scoped_employees(viewer)
    stages = pipeline.enabled_stages()
    metrics = {}

    for stage_key in stages:
        # Employees who have completed this stage
        completed_statuses = _statuses_after_stage(stage_key, stages)
        completed = employees.filter(status__in=completed_statuses).count()

        # All employees who have reached this stage
        reached_statuses = _statuses_from_stage(stage_key, stages)
        total = employees.filter(status__in=reached_statuses).count()

        rate = (completed / total * 100) if total > 0 else 0

        metrics[stage_key] = {
            'label': pipeline.STAGE_LABELS.get(stage_key, stage_key),
            'completed': completed,
            'total': total,
            'completion_rate': round(rate, 1),
        }

    return metrics


def get_overdue_metrics(viewer=None):
    """
    Get overdue employee count by stage.

    Returns: {stage_key: {overdue: N, at_risk: N}}
    """
    employees = _get_scoped_employees(viewer)
    now = timezone.now()
    stages = pipeline.enabled_stages()
    metrics = {}

    for stage_key in stages:
        # Employees currently in this stage
        current_statuses = _statuses_at_stage(stage_key, stages)
        current = employees.filter(status__in=current_statuses)

        # Overdue: due_date < now
        overdue = current.filter(
            stage_due_date__isnull=False,
            stage_due_date__lt=now
        ).count()

        # At risk: due_date within 3 days
        at_risk_date = now + timedelta(days=3)
        at_risk = current.filter(
            stage_due_date__isnull=False,
            stage_due_date__gte=now,
            stage_due_date__lte=at_risk_date
        ).count()

        metrics[stage_key] = {
            'label': pipeline.STAGE_LABELS.get(stage_key, stage_key),
            'overdue': overdue,
            'at_risk': at_risk,
        }

    return metrics


def get_time_to_completion_metrics(viewer=None):
    """
    Get average time-to-completion for each stage.

    Requires employees with stage_entered_at timestamps.
    Returns average days in stage.
    """
    employees = _get_scoped_employees(viewer)
    stages = pipeline.enabled_stages()
    metrics = {}

    for stage_key in stages:
        # Employees who have completed this stage
        completed_statuses = _statuses_after_stage(stage_key, stages)
        completed_qs = employees.filter(
            status__in=completed_statuses,
            stage_entered_at__isnull=False,
            stage_due_date__isnull=False
        )

        if not completed_qs.exists():
            metrics[stage_key] = {
                'label': pipeline.STAGE_LABELS.get(stage_key, stage_key),
                'avg_days': 0,
                'count': 0,
            }
            continue

        # Calculate average days from entered to due date
        avg_result = completed_qs.aggregate(
            avg_days=Avg(F('stage_due_date') - F('stage_entered_at'))
        )

        avg_timedelta = avg_result.get('avg_days')
        avg_days = avg_timedelta.days if avg_timedelta else 0

        metrics[stage_key] = {
            'label': pipeline.STAGE_LABELS.get(stage_key, stage_key),
            'avg_days': avg_days,
            'count': completed_qs.count(),
        }

    return metrics


def get_department_breakdown(viewer=None):
    """
    Get employee count and completion rate by department.

    Returns list of dicts with dept name, count, and completion %.
    """
    employees = _get_scoped_employees(viewer)
    depts = employees.values('department__name').annotate(
        total=Count('id'),
        completed=Count(
            Case(When(status='completed', then=1), output_field=IntegerField())
        )
    ).order_by('-total')

    breakdown = []
    for dept in depts:
        total = dept['total']
        completed = dept['completed']
        rate = (completed / total * 100) if total > 0 else 0

        breakdown.append({
            'department': dept['department__name'] or 'Unassigned',
            'total': total,
            'completed': completed,
            'completion_rate': round(rate, 1),
        })

    return breakdown


def get_summary_stats(viewer=None):
    """
    Get high-level summary statistics.

    Returns: {total, completed, in_progress, overdue, avg_completion_days}
    """
    now = timezone.now()
    employees = _get_scoped_employees(viewer)

    total = employees.count()
    completed = employees.filter(status='completed').count()
    in_progress = employees.exclude(status__in=['completed', 'pending', 'deleted']).count()
    overdue = employees.exclude(status='completed').filter(
        stage_due_date__isnull=False,
        stage_due_date__lt=now
    ).count()

    # Average completion time (days from first joining to completion)
    completed_qs = employees.filter(
        status='completed',
        created_at__isnull=False,
        updated_at__isnull=False
    )

    avg_days = 0
    if completed_qs.exists():
        avg_result = completed_qs.aggregate(
            avg_days=Avg(F('updated_at') - F('created_at'))
        )
        avg_timedelta = avg_result.get('avg_days')
        avg_days = avg_timedelta.days if avg_timedelta else 0

    return {
        'total': total,
        'completed': completed,
        'in_progress': in_progress,
        'overdue': overdue,
        'completion_rate': round(completed / total * 100, 1) if total > 0 else 0,
        'avg_completion_days': avg_days,
    }


def get_training_analytics(viewer=None):
    """
    Learning path and quiz analytics.

    Returns: dict with paths list + summary totals.
    """
    paths = Content.objects.filter(kind='learning_path', is_active=True)
    results = []

    total_enrollments = 0
    total_completed = 0

    scoped_users = _get_scoped_employees(viewer)

    for path in paths:
        enrolled = Engagement.objects.filter(kind='enrollment', content=path, user__in=scoped_users)
        count = enrolled.count()
        completed = enrolled.filter(status='completed').count()
        overdue = enrolled.exclude(status='completed').filter(
            due_date__isnull=False, due_date__lt=timezone.now().date()
        ).count()

        rate = round(completed / count * 100, 1) if count > 0 else 0.0
        total_enrollments += count
        total_completed += completed

        # Quiz performance across modules in this path
        module_ids = [m.get('content_id') for m in path.meta.get('modules', []) if m.get('content_id')]
        quiz_scores = []
        for mid in module_ids:
            try:
                module = Content.objects.get(id=mid, kind='training')
                for eng in Engagement.objects.filter(kind='enrollment', content=module, user__in=scoped_users):
                    for attempt in eng.data.get('progress', {}).get('quiz_attempts', []):
                        if attempt.get('score_percentage') is not None:
                            quiz_scores.append(attempt['score_percentage'])
            except Content.DoesNotExist:
                pass

        avg_score = round(sum(quiz_scores) / len(quiz_scores), 1) if quiz_scores else None

        results.append({
            'id': path.id,
            'title': path.title,
            'enrollments': count,
            'completed': completed,
            'overdue': overdue,
            'completion_rate': rate,
            'avg_quiz_score': avg_score,
        })

    results.sort(key=lambda x: x['enrollments'], reverse=True)

    return {
        'paths': results,
        'total_enrollments': total_enrollments,
        'total_completed': total_completed,
        'total_paths': len(results),
        'overall_rate': round(total_completed / total_enrollments * 100, 1) if total_enrollments > 0 else 0.0,
    }


def get_session_analytics(viewer=None):
    """
    Session/orientation attendance analytics.

    Returns: dict with sessions list + type breakdown.
    """
    sessions = Content.objects.filter(kind='live_session')
    total = sessions.count()

    TYPE_LABELS = {
        'orientation': 'Orientation',
        '30_day_review': '30-Day Review',
        '60_day_review': '60-Day Review',
        '90_day_review': '90-Day Review',
        'training': 'Training Session',
        'meeting': 'General Meeting',
    }

    by_type = {}
    for s in sessions:
        t = s.meta.get('session_type', 'unknown')
        if t not in by_type:
            by_type[t] = {'label': TYPE_LABELS.get(t, t.title()), 'count': 0, 'total_registered': 0, 'total_attended': 0}
        by_type[t]['count'] += 1

    # Attendance breakdown
    feedback_data = []
    scoped_users = _get_scoped_employees(viewer)

    eng_qs = Engagement.objects.filter(kind='session').select_related('content', 'user')
    eng_qs = eng_qs.filter(user__in=scoped_users)

    for eng in eng_qs:
        if not eng.content:
            continue
        t = eng.content.meta.get('session_type', 'unknown')
        if t not in by_type:
            by_type[t] = {'label': TYPE_LABELS.get(t, t.title()), 'count': 0, 'total_registered': 0, 'total_attended': 0}
        for att in eng.data.get('attendees', []):
            by_type[t]['total_registered'] += 1
            if att.get('status') == 'attended':
                by_type[t]['total_attended'] += 1

        fb = eng.data.get('feedback')
        if fb:
            feedback_data.append({
                'user_name': eng.user.full_name,
                'session_title': eng.content.title,
                'session_type': TYPE_LABELS.get(t, t),
                'rating': fb.get('rating', 0),
                'comment': fb.get('comment', ''),
            })

    # Compute attendance rates per type
    type_breakdown = []
    for t, data in by_type.items():
        reg = data['total_registered']
        att = data['total_attended']
        type_breakdown.append({
            'type': t,
            'label': data['label'],
            'sessions': data['count'],
            'registered': reg,
            'attended': att,
            'attendance_rate': round(att / reg * 100, 1) if reg > 0 else 0.0,
        })
    type_breakdown.sort(key=lambda x: x['sessions'], reverse=True)

    # Recent sessions with attendance info
    recent_sessions = []
    for s in sessions.order_by('-created_at')[:20]:
        engs = Engagement.objects.filter(kind='session', content=s, user__in=scoped_users)
        registered = 0
        attended = 0
        for eng in engs:
            for att in eng.data.get('attendees', []):
                registered += 1
                if att.get('status') == 'attended':
                    attended += 1
        recent_sessions.append({
            'id': s.id,
            'title': s.title,
            'type': TYPE_LABELS.get(s.meta.get('session_type', ''), 'Session'),
            'date': s.meta.get('scheduled_date', '')[:10],
            'status': s.meta.get('status', ''),
            'registered': registered,
            'attended': attended,
            'attendance_rate': round(attended / registered * 100, 1) if registered > 0 else 0.0,
        })

    # Average feedback rating
    all_ratings = [f['rating'] for f in feedback_data if f['rating']]
    avg_rating = round(sum(all_ratings) / len(all_ratings), 1) if all_ratings else None

    return {
        'total_sessions': total,
        'type_breakdown': type_breakdown,
        'recent_sessions': recent_sessions,
        'feedback': feedback_data[:30],
        'avg_rating': avg_rating,
        'total_feedback': len(feedback_data),
    }


# Helper functions
def _statuses_from_stage(stage_key, stages):
    """Get all statuses from this stage onwards (including this stage)."""
    try:
        idx = list(stages).index(stage_key)
        return stages[idx:] + ['completed']
    except (ValueError, IndexError):
        return [stage_key, 'completed']


def _statuses_after_stage(stage_key, stages):
    """Get all statuses after this stage (not including this stage)."""
    try:
        idx = list(stages).index(stage_key)
        return stages[idx + 1:] + ['completed']
    except (ValueError, IndexError):
        return ['completed']


def _statuses_at_stage(stage_key, stages):
    """Get statuses for employees currently at this stage."""
    return [stage_key]
