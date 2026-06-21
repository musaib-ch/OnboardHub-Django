"""
30/60/90 day onboarding plan service.

Manages creation, assignment, and tracking of milestone-based onboarding plans.
"""
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from django.utils import timezone

from ..models import Engagement, User, Content


# Default 30/60/90 plan template
DEFAULT_PLAN_TEMPLATE = {
    'day_30': {
        'label': '30 Days',
        'description': 'Complete onboarding fundamentals and team integration',
        'milestones': [
            {'title': 'Complete orientation', 'completed': False, 'due_days': 5},
            {'title': 'Meet team members', 'completed': False, 'due_days': 7},
            {'title': 'Understand role responsibilities', 'completed': False, 'due_days': 14},
            {'title': 'First month 1:1 review', 'completed': False, 'due_days': 30},
        ],
        'posts': [],
    },
    'day_60': {
        'label': '60 Days',
        'description': 'Develop competencies and take on first projects',
        'milestones': [
            {'title': 'Lead first project/task', 'completed': False, 'due_days': 45},
            {'title': 'Build relationships across teams', 'completed': False, 'due_days': 50},
            {'title': 'Achieve proficiency targets', 'completed': False, 'due_days': 60},
            {'title': 'Second month performance check-in', 'completed': False, 'due_days': 60},
        ],
        'posts': [],
    },
    'day_90': {
        'label': '90 Days',
        'description': 'Operate independently and contribute fully',
        'milestones': [
            {'title': 'Complete major project independently', 'completed': False, 'due_days': 75},
            {'title': 'Demonstrate core competencies', 'completed': False, 'due_days': 85},
            {'title': 'Contribute to team goals', 'completed': False, 'due_days': 90},
            {'title': 'Final probation review', 'completed': False, 'due_days': 90},
        ],
        'posts': [],
    },
}


def create_plan(employee: User, creator: User, template: Dict = None) -> Engagement:
    """
    Create a 30/60/90 day plan for an employee.

    Args:
        employee: Employee receiving the plan
        creator: HRBP/Manager creating the plan
        template: Custom plan template (uses default if None)

    Returns:
        Engagement object with plan data
    """
    if template is None:
        template = DEFAULT_PLAN_TEMPLATE

    plan_data = {
        'plan': template,
        'created_by_id': creator.id,
        'created_by_name': creator.full_name,
        'created_at': timezone.now().isoformat(),
        'employee_id': employee.id,
        'employee_joining_date': employee.date_of_joining.isoformat() if employee.date_of_joining else None,
        'status': 'active',  # active, completed, paused
    }

    # Create or update engagement record
    engagement, created = Engagement.objects.update_or_create(
        user=employee,
        kind='onboarding_plan',
        defaults={
            'content': None,
            'data': plan_data,
        }
    )

    return engagement


def get_plan(employee: User) -> Optional[Dict]:
    """Get employee's 30/60/90 plan."""
    try:
        engagement = Engagement.objects.get(user=employee, kind='onboarding_plan')
        return engagement.data
    except Engagement.DoesNotExist:
        return None


def update_milestone(employee: User, phase: str, milestone_index: int, completed: bool) -> bool:
    """
    Mark a milestone as completed.

    Args:
        employee: Employee
        phase: 'day_30', 'day_60', or 'day_90'
        milestone_index: Index of milestone in that phase
        completed: True to mark complete

    Returns:
        True if updated successfully
    """
    try:
        engagement = Engagement.objects.get(user=employee, kind='onboarding_plan')
        plan_data = engagement.data

        if phase in plan_data.get('plan', {}):
            phase_data = plan_data['plan'][phase]
            if 0 <= milestone_index < len(phase_data.get('milestones', [])):
                phase_data['milestones'][milestone_index]['completed'] = completed
                if completed:
                    phase_data['milestones'][milestone_index]['completed_at'] = timezone.now().isoformat()
                engagement.data = plan_data
                engagement.save()
                return True

    except Engagement.DoesNotExist:
        pass

    return False


def post_update(employee: User, phase: str, author: User, message: str, author_role: str = None) -> bool:
    """
    Post an update/comment on a phase of the plan.

    Args:
        employee: Employee
        phase: 'day_30', 'day_60', or 'day_90'
        author: User posting the update
        message: Update message
        author_role: Role of author (for display)

    Returns:
        True if posted successfully
    """
    try:
        engagement = Engagement.objects.get(user=employee, kind='onboarding_plan')
        plan_data = engagement.data

        if phase in plan_data.get('plan', {}):
            phase_data = plan_data['plan'][phase]

            post = {
                'id': len(phase_data.get('posts', [])),
                'author_id': author.id,
                'author_name': author.full_name,
                'author_role': author_role or author.role,
                'message': message,
                'posted_at': timezone.now().isoformat(),
            }

            if 'posts' not in phase_data:
                phase_data['posts'] = []

            phase_data['posts'].append(post)
            engagement.data = plan_data
            engagement.save()

            # Log activity
            from . import log_activity
            log_activity(
                None,
                action='post_plan_update',
                entity_type='onboarding_plan',
                description=f'{author.full_name} posted update on {phase} for {employee.full_name}'
            )

            return True

    except Engagement.DoesNotExist:
        pass

    return False


def get_progress_stats(employee: User) -> Dict:
    """
    Get progress statistics for 30/60/90 plan.

    Returns:
        {
            'total_milestones': int,
            'completed_milestones': int,
            'completion_percentage': int,
            'phases': {
                'day_30': {'total': int, 'completed': int, 'percentage': int},
                'day_60': {'total': int, 'completed': int, 'percentage': int},
                'day_90': {'total': int, 'completed': int, 'percentage': int},
            }
        }
    """
    plan_data = get_plan(employee)

    if not plan_data:
        return {
            'total_milestones': 0,
            'completed_milestones': 0,
            'completion_percentage': 0,
            'phases': {},
        }

    plan = plan_data.get('plan', {})
    total_milestones = 0
    completed_milestones = 0
    phases_stats = {}

    for phase_key in ['day_30', 'day_60', 'day_90']:
        phase = plan.get(phase_key, {})
        milestones = phase.get('milestones', [])
        phase_completed = sum(1 for m in milestones if m.get('completed', False))
        phase_total = len(milestones)

        phases_stats[phase_key] = {
            'total': phase_total,
            'completed': phase_completed,
            'percentage': int((phase_completed / phase_total * 100) if phase_total > 0 else 0),
            'label': phase.get('label', phase_key),
        }

        total_milestones += phase_total
        completed_milestones += phase_completed

    return {
        'total_milestones': total_milestones,
        'completed_milestones': completed_milestones,
        'completion_percentage': int((completed_milestones / total_milestones * 100) if total_milestones > 0 else 0),
        'phases': phases_stats,
    }


def get_phase_status(employee: User, phase: str) -> Dict:
    """Get detailed status of a specific phase."""
    plan_data = get_plan(employee)

    if not plan_data:
        return {}

    phase_data = plan_data.get('plan', {}).get(phase, {})

    return {
        'label': phase_data.get('label'),
        'description': phase_data.get('description'),
        'milestones': phase_data.get('milestones', []),
        'posts': phase_data.get('posts', []),
    }


def get_due_date(employee: User, phase: str) -> Optional[str]:
    """Get the due date for completing a phase."""
    if not employee.date_of_joining:
        return None

    phase_days = {
        'day_30': 30,
        'day_60': 60,
        'day_90': 90,
    }

    if phase not in phase_days:
        return None

    due_date = employee.date_of_joining + timedelta(days=phase_days[phase])
    return due_date.isoformat()


def is_phase_overdue(employee: User, phase: str) -> bool:
    """Check if a phase is overdue."""
    due_date_str = get_due_date(employee, phase)
    if not due_date_str:
        return False

    due_date = datetime.fromisoformat(due_date_str).date()
    return due_date < timezone.now().date()


def get_days_until_phase_due(employee: User, phase: str) -> Optional[int]:
    """Get number of days until phase is due. Returns negative if overdue."""
    due_date_str = get_due_date(employee, phase)
    if not due_date_str:
        return None

    due_date = datetime.fromisoformat(due_date_str).date()
    return (due_date - timezone.now().date()).days
