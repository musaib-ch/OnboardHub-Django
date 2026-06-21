"""
Analytics service for onboarding metrics and reporting.

Provides metrics on stage completion, time-to-completion, funnel analysis, etc.
"""
from datetime import timedelta
from django.db.models import Q, Count, Avg, F, Case, When, IntegerField
from django.utils import timezone
from .. import pipeline
from ..models import User


def get_onboarding_funnel():
    """
    Get funnel metrics: how many employees at each stage.

    Returns dict with stage counts and percentages.
    """
    all_employees = User.objects.filter(role='employee').exclude(status='deleted').count()

    if not all_employees:
        return {}

    stages = pipeline.enabled_stages()
    funnel = {}

    for stage_key in stages:
        # Count employees who have reached this stage or beyond
        status_list = _statuses_from_stage(stage_key, stages)
        count = User.objects.filter(role='employee', status__in=status_list).exclude(
            status='deleted'
        ).count()

        percentage = (count / all_employees * 100) if all_employees else 0

        funnel[stage_key] = {
            'label': pipeline.STAGE_LABELS.get(stage_key, stage_key),
            'count': count,
            'percentage': round(percentage, 1),
        }

    return funnel


def get_stage_completion_metrics():
    """
    Get completion metrics for each stage.

    Returns: {stage_key: {completed: N, total: N, rate: %}}
    """
    stages = pipeline.enabled_stages()
    metrics = {}

    for stage_key in stages:
        # Employees who have completed this stage
        completed_statuses = _statuses_after_stage(stage_key, stages)
        completed = User.objects.filter(
            role='employee', status__in=completed_statuses
        ).exclude(status='deleted').count()

        # All employees who have reached this stage
        reached_statuses = _statuses_from_stage(stage_key, stages)
        total = User.objects.filter(
            role='employee', status__in=reached_statuses
        ).exclude(status='deleted').count()

        rate = (completed / total * 100) if total > 0 else 0

        metrics[stage_key] = {
            'label': pipeline.STAGE_LABELS.get(stage_key, stage_key),
            'completed': completed,
            'total': total,
            'completion_rate': round(rate, 1),
        }

    return metrics


def get_overdue_metrics():
    """
    Get overdue employee count by stage.

    Returns: {stage_key: {overdue: N, at_risk: N}}
    """
    now = timezone.now()
    stages = pipeline.enabled_stages()
    metrics = {}

    for stage_key in stages:
        # Employees currently in this stage
        current_statuses = _statuses_at_stage(stage_key, stages)
        current = User.objects.filter(
            role='employee', status__in=current_statuses
        ).exclude(status='deleted')

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


def get_time_to_completion_metrics():
    """
    Get average time-to-completion for each stage.

    Requires employees with stage_entered_at timestamps.
    Returns average days in stage.
    """
    stages = pipeline.enabled_stages()
    metrics = {}

    for stage_key in stages:
        # Employees who have completed this stage
        completed_statuses = _statuses_after_stage(stage_key, stages)
        completed_qs = User.objects.filter(
            role='employee',
            status__in=completed_statuses,
            stage_entered_at__isnull=False,
            stage_due_date__isnull=False
        ).exclude(status='deleted')

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


def get_department_breakdown():
    """
    Get employee count and completion rate by department.

    Returns list of dicts with dept name, count, and completion %.
    """
    depts = User.objects.filter(
        role='employee'
    ).exclude(status='deleted').values('department__name').annotate(
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


def get_summary_stats():
    """
    Get high-level summary statistics.

    Returns: {total, completed, in_progress, overdue, avg_completion_days}
    """
    now = timezone.now()
    employees = User.objects.filter(role='employee').exclude(status='deleted')

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
