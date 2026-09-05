"""
Unified stage system - treats all onboarding components as stages.

Medical, Pre-Onboarding, Onboarding, Post-Onboarding, Orientation,
Training, 30/60/90 are all "stages" with activities/data.
"""
from typing import Dict, List, Optional
from django.utils import timezone

from ..models import User, Engagement, Content
from .onboarding_plan_service import get_plan, get_progress_stats


# Stage definitions with their data sources - ordered by logical onboarding journey
UNIFIED_STAGES = {
    'offer': {
        'label': 'Offer Acceptance',
        'icon': 'bi-file-earmark-check',
        'color': 'primary',
        'description': 'Offer document review and acceptance',
        'activities_source': 'offer_records',
    },
    'medical': {
        'label': 'Medical Upload',
        'icon': 'bi-heart-pulse',
        'color': 'danger',
        'description': 'Medical document review',
        'activities_source': 'medical_records',
    },
    'pre_onboarding': {
        'label': 'Pre-Onboarding',
        'icon': 'bi-clipboard-check',
        'color': 'info',
        'description': 'Pre-onboarding setup and forms',
        'activities_source': 'forms_engagement',
    },
    'onboarding': {
        'label': 'Onboarding',
        'icon': 'bi-person-check',
        'color': 'secondary',
        'description': 'Onboarding documents and forms',
        'activities_source': 'forms_engagement',
    },
    'post_onboarding': {
        'label': 'Post-Onboarding',
        'icon': 'bi-check-circle',
        'color': 'info',
        'description': 'Post-onboarding review and feedback',
        'activities_source': 'forms_engagement',
    },
    'orientation': {
        'label': 'Orientation',
        'icon': 'bi-compass',
        'color': 'primary',
        'description': 'Orientation sessions and initial setup',
        'activities_source': 'orientation_sessions',
    },
    'training': {
        'label': 'Training & Learning',
        'icon': 'bi-mortarboard',
        'color': 'success',
        'description': 'Learning paths and course completion',
        'activities_source': 'training_engagement',
    },
    'onboarding_30_60_90': {
        'label': '30/60/90 Plan',
        'icon': 'bi-calendar3',
        'color': 'warning',
        'description': '30, 60, and 90-day milestone plan',
        'activities_source': 'onboarding_plan',
    },
}


def get_employee_stage_activities(employee: User, stage: str) -> Dict:
    """
    Get all activities/data for an employee at a specific stage.

    Returns unified structure with activities, status, progress, etc.
    """
    activities_source = UNIFIED_STAGES.get(stage, {}).get('activities_source')

    if not activities_source:
        return {'activities': [], 'status': 'unknown'}

    if activities_source == 'offer_records':
        return _get_offer_activities(employee, stage)
    elif activities_source == 'medical_records':
        return _get_medical_activities(employee, stage)
    elif activities_source == 'forms_engagement':
        return _get_forms_activities(employee, stage)
    elif activities_source == 'orientation_sessions':
        return _get_orientation_activities(employee, stage)
    elif activities_source == 'training_engagement':
        return _get_training_activities(employee, stage)
    elif activities_source == 'onboarding_plan':
        return _get_onboarding_plan_activities(employee, stage)

    return {'activities': [], 'status': 'unknown'}


def _get_offer_activities(employee: User, stage: str) -> Dict:
    """Get offer records for an employee as activities."""
    try:
        from ..models_offers import Offer
        from django.db.models import Q

        offers = Offer.objects.filter(
            Q(candidate_user=employee) | Q(candidate_email__iexact=employee.email)
        ).order_by('-created_at')

        activities = [
            {
                'id': o.id,
                'type': 'offer_letter',
                'title': f"Offer #{o.id}",
                'status': o.status,
                'description': f"Status: {o.get_status_display()}",
                'created_at': o.created_at.isoformat() if o.created_at else None,
            }
            for o in offers
        ]

        completed = sum(1 for a in activities if a['status'] in ['accepted', 'signed'])
        total = len(activities)

        return {
            'activities': activities,
            'status': 'completed' if completed > 0 else ('pending' if activities else 'unassigned'),
            'progress': {
                'completed': completed,
                'total': total,
                'percentage': int((completed / total * 100) if total > 0 else 0),
            }
        }
    except Exception:
        return {'activities': [], 'status': 'unknown'}



def _get_medical_activities(employee: User, stage: str) -> Dict:
    """Get medical records as activities."""
    from ..models import MedicalRecord

    try:
        records = MedicalRecord.objects.filter(user=employee)
        activities = [
            {
                'id': r.id,
                'type': 'medical_document',
                'title': r.requirement_name,
                'status': r.status,
                'description': r.description or '',
                'file': str(r.file.url) if r.file else None,
                'created_at': r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]

        completed = sum(1 for a in activities if a['status'] == 'approved')
        total = len(activities)

        return {
            'activities': activities,
            'status': employee.status,
            'progress': {
                'completed': completed,
                'total': total,
                'percentage': int((completed / total * 100) if total > 0 else 0),
            }
        }
    except:
        return {'activities': [], 'status': 'unknown'}


def _get_forms_activities(employee: User, stage: str) -> Dict:
    """Get form responses as activities."""
    from ..models import Form, FormResponse

    try:
        # Get forms for this stage
        stage_forms = Form.objects.filter(
            data__stages__contains=stage
        ) if hasattr(Form.objects.first(), 'data') else Form.objects.all()

        activities = []
        for form in stage_forms[:10]:  # Limit to 10
            try:
                response = FormResponse.objects.filter(
                    user=employee,
                    form=form
                ).latest('created_at')

                activities.append({
                    'id': response.id,
                    'type': 'form_response',
                    'title': form.title,
                    'status': response.data.get('status', 'pending'),
                    'description': form.description or '',
                    'created_at': response.created_at.isoformat(),
                    'updated_at': response.updated_at.isoformat(),
                })
            except FormResponse.DoesNotExist:
                activities.append({
                    'id': form.id,
                    'type': 'form',
                    'title': form.title,
                    'status': 'not_started',
                    'description': form.description or '',
                })

        completed = sum(1 for a in activities if a['status'] in ['submitted', 'approved'])
        total = len(activities)

        return {
            'activities': activities,
            'status': employee.status,
            'progress': {
                'completed': completed,
                'total': total,
                'percentage': int((completed / total * 100) if total > 0 else 0),
            }
        }
    except:
        return {'activities': [], 'status': 'unknown'}


def _get_orientation_activities(employee: User, stage: str) -> Dict:
    """Get orientation sessions as activities."""
    from ..services.session_service import list_sessions

    try:
        sessions = list_sessions()

        # Filter orientation sessions for this employee
        activities = []
        for session in sessions:
            if session.meta.get('session_type') == 'orientation':
                # Check if employee is registered
                registrations = Engagement.objects.filter(
                    kind='session',
                    content_id=session.id,
                    user=employee
                )

                if registrations.exists():
                    reg = registrations.first()
                    activities.append({
                        'id': session.id,
                        'type': 'session',
                        'title': session.title,
                        'status': reg.data.get('status', 'registered'),
                        'description': session.description or '',
                        'scheduled_date': session.meta.get('scheduled_date'),
                        'zoom_link': session.meta.get('zoom_join_url'),
                    })

        return {
            'activities': activities,
            'status': 'active' if activities else 'pending',
            'progress': {
                'completed': sum(1 for a in activities if a['status'] == 'attended'),
                'total': len(activities),
                'percentage': int((sum(1 for a in activities if a['status'] == 'attended') / len(activities) * 100) if activities else 0),
            }
        }
    except:
        return {'activities': [], 'status': 'unknown'}


def _get_training_activities(employee: User, stage: str) -> Dict:
    """Get training and learning path progress as activities."""
    try:
        engagements = Engagement.objects.filter(
            user=employee,
            kind__in=['training', 'training_path']
        )

        activities = []
        for eng in engagements:
            activities.append({
                'id': eng.id,
                'type': 'training',
                'title': eng.content.title if eng.content else 'Training',
                'status': eng.data.get('status', 'active'),
                'description': eng.content.description if eng.content else '',
                'progress': eng.data.get('progress', {}).get('completion_percentage', 0),
                'started_at': eng.created_at.isoformat() if eng.created_at else None,
            })

        completed = sum(1 for a in activities if a['status'] == 'completed')
        total = len(activities)

        return {
            'activities': activities,
            'status': 'active' if activities else 'pending',
            'progress': {
                'completed': completed,
                'total': total,
                'percentage': int((completed / total * 100) if total > 0 else 0),
            }
        }
    except:
        return {'activities': [], 'status': 'unknown'}


def _get_onboarding_plan_activities(employee: User, stage: str) -> Dict:
    """Get 30/60/90 plan progress as activities."""
    try:
        plan = get_plan(employee)
        if not plan:
            return {'activities': [], 'status': 'not_assigned'}

        stats = get_progress_stats(employee)

        activities = [
            {
                'id': f'day_{day}',
                'type': 'milestone_phase',
                'title': stats['phases'][f'day_{day}']['label'],
                'status': 'completed' if stats['phases'][f'day_{day}']['percentage'] == 100 else 'in_progress',
                'progress': stats['phases'][f'day_{day}']['percentage'],
                'completed': stats['phases'][f'day_{day}']['completed'],
                'total': stats['phases'][f'day_{day}']['total'],
            }
            for day in [30, 60, 90]
        ]

        return {
            'activities': activities,
            'status': plan.get('status', 'active'),
            'progress': {
                'completed': stats['completed_milestones'],
                'total': stats['total_milestones'],
                'percentage': stats['completion_percentage'],
            }
        }
    except:
        return {'activities': [], 'status': 'unknown'}


def get_employee_all_stages(employee: User) -> List[Dict]:
    """Get all stages and their activities for an employee in profile view.

    Mandatory stages (medical, pre_onboarding, onboarding, post_onboarding)
    always show lock/unlock status.

    Optional stages (orientation, training, 30/60/90) show unassigned if no activities.

    Status is synced with employee's actual workflow state.
    """
    stages = []

    # Stages that are always assigned/mandatory
    mandatory_stages = {'offer', 'medical', 'pre_onboarding', 'onboarding', 'post_onboarding'}

    # Track which stages are completed for lock/unlock logic
    completed_stages = set()

    # Parse employee's current status to determine which stages are done
    # Status format: "pending" | "offer" | "medical" | "pre_onboarding" | "onboarding" | "post_onboarding" | "completed"
    raw_status = employee.status.lower() if employee.status else 'pending'
    from ..pipeline import stage_of_status
    employee_status = stage_of_status(raw_status) or raw_status
    if employee_status == '__done__':
        employee_status = 'completed'

    for stage_key, stage_config in UNIFIED_STAGES.items():
        activities_data = get_employee_stage_activities(employee, stage_key)
        activities = activities_data.get('activities', [])
        raw_status = activities_data.get('status', 'unknown')

        is_mandatory = stage_key in mandatory_stages
        is_locked = _is_stage_locked(stage_key, completed_stages)
        has_activities = activities and len(activities) > 0
        is_current_stage = (employee_status == stage_key)  # Direct comparison

        # Determine display status based on employee's workflow position
        if is_mandatory:
            # Mandatory stages: Show lock/unlock status
            if _is_stage_before_current(stage_key, employee_status):
                # This stage is before the current stage - it's completed
                display_status = 'completed'
                completed_stages.add(stage_key)
            elif is_current_stage or (employee_status in ('pending', 'offer') and stage_key == 'offer'):
                if has_activities:
                    if _any_activity_approved(activities):
                        display_status = 'completed'
                        completed_stages.add(stage_key)
                    elif _any_activity_submitted(activities):
                        display_status = 'pending'
                    else:
                        display_status = 'pending'
                else:
                    display_status = 'pending'
            elif is_locked:
                # Prerequisites not met
                display_status = 'locked'
            else:
                # This stage is after the current stage - it's locked
                display_status = 'locked'
        else:
            # Optional stages: Show unassigned if no activities
            if not has_activities:
                display_status = 'unassigned'
            elif _any_activity_approved(activities):
                display_status = 'completed'
                completed_stages.add(stage_key)
            elif _any_activity_submitted(activities):
                display_status = 'pending'
            else:
                display_status = 'pending'

        stages.append({
            'key': stage_key,
            'label': stage_config['label'],
            'icon': stage_config['icon'],
            'color': stage_config['color'],
            'description': stage_config['description'],
            'status': display_status,
            'activities': activities,
            'progress': activities_data.get('progress', {}),
            'is_active': is_current_stage,
        })

    return stages


def _is_stage_locked(stage_key: str, completed_stages: set) -> bool:
    """Determine if a stage should be locked based on prerequisites."""
    # Define stage dependencies - which stages must be completed before this one unlocks
    stage_dependencies = {
        'offer': set(),  # Offer has no prerequisites
        'medical': set(),  # Medical has no strict prerequisite
        'pre_onboarding': {'medical'},  # Pre-onboarding requires medical to be completed
        'onboarding': {'pre_onboarding'},  # Onboarding requires pre-onboarding to be completed
        'post_onboarding': {'onboarding'},  # Post-onboarding requires onboarding to be completed
        'orientation': set(),  # Orientation can start anytime
        'training': set(),  # Training can start anytime
        'onboarding_30_60_90': {'onboarding'},  # 30/60/90 plan starts after onboarding begins
    }

    # Get the required prerequisites for this stage
    required = stage_dependencies.get(stage_key, set())

    # Stage is locked if any required prerequisite is not completed
    return not required.issubset(completed_stages)


def _is_stage_before_current(stage_key: str, employee_status: str) -> bool:
    """Check if a stage comes before the employee's current stage in the workflow."""
    # Define the mandatory workflow order
    workflow_order = ['offer', 'medical', 'pre_onboarding', 'onboarding', 'post_onboarding']

    try:
        stage_index = workflow_order.index(stage_key)

        # Find where employee is in the workflow
        # Employee status matches one of: "pending", "medical", "pre_onboarding", "onboarding", "post_onboarding", "completed"
        for current_stage in workflow_order:
            # Direct comparison - no transformations needed
            if employee_status == current_stage:
                current_index = workflow_order.index(current_stage)
                return stage_index < current_index

        # If employee_status is "pending", they haven't started any stage yet
        if employee_status == 'pending':
            return False  # No stage is "before" pending

        # If employee_status is "completed", all mandatory stages are before that
        if employee_status == 'completed':
            return True

    except (ValueError, AttributeError):
        return False

    return False


def _any_activity_approved(activities: list) -> bool:
    """Check if any activity has an approved status."""
    return any(
        act.get('status') in ['approved', 'completed', 'done']
        for act in activities
    )


def _any_activity_submitted(activities: list) -> bool:
    """Check if any activity has been submitted but not yet approved."""
    return any(
        act.get('status') in ['submitted', 'pending', 'in_progress', 'reviewing']
        for act in activities
    )


def is_super_admin_or_has_perm(user: User, permission: str) -> bool:
    """Check if user is super_admin OR has specific permission."""
    if user.role == 'super_admin':
        return True
    return user.has_perm_key(permission)
