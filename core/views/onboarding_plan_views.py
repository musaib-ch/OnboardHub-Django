"""
30/60/90 day onboarding plan views.

HRBP/Manager views for creating/managing plans.
Employee views for tracking progress and posting updates.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ..models import User, Engagement
from ..decorators import permission_required, roles_required
from ..services.onboarding_plan_service import (
    create_plan,
    get_plan,
    get_progress_stats,
    get_phase_status,
    update_milestone,
    post_update,
    DEFAULT_PLAN_TEMPLATE,
)
from ..services.email_triggers import send_onboarding_plan_assigned, send_onboarding_plan_feedback
from ..services.notification_service import should_send_email
from ..services import log_activity


# ─────────────────────────────────────────────────────────────────────────────
# EMPLOYEE VIEWS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def my_onboarding_plan(request):
    """Employee view of their 30/60/90 plan."""
    user = request.user

    # Only employees can view their own plan
    if user.role != 'employee':
        return render(request, '403.html', status=403)

    plan_data = get_plan(user)
    progress = get_progress_stats(user)

    ctx = {
        'plan_data': plan_data,
        'progress': progress,
        'phases': {
            'day_30': get_phase_status(user, 'day_30'),
            'day_60': get_phase_status(user, 'day_60'),
            'day_90': get_phase_status(user, 'day_90'),
        },
    }

    return render(request, 'onboarding_plan/employee_plan.html', ctx)


@login_required
@require_http_methods(['POST'])
def mark_milestone_complete(request, milestone_id):
    """Mark a milestone as complete."""
    user = request.user
    phase = request.POST.get('phase')
    milestone_index = int(request.POST.get('milestone_index', 0))

    if update_milestone(user, phase, milestone_index, True):
        log_activity(request, action='complete_milestone', entity_type='onboarding_plan',
                    description=f'Completed milestone in {phase}')
        messages.success(request, 'Milestone marked as complete!')
    else:
        messages.error(request, 'Could not update milestone.')

    return redirect('my_onboarding_plan')


@login_required
@require_http_methods(['POST'])
def post_plan_update(request, phase):
    """Post an update on a plan phase."""
    user = request.user
    message = request.POST.get('message', '').strip()

    if not message:
        messages.error(request, 'Message cannot be empty.')
        return redirect('my_onboarding_plan')

    if post_update(user, phase, user, message):
        log_activity(request, action='post_plan_update', entity_type='onboarding_plan',
                    description=f'Posted update on {phase}')
        messages.success(request, 'Update posted!')
    else:
        messages.error(request, 'Could not post update.')

    return redirect('my_onboarding_plan')


# ─────────────────────────────────────────────────────────────────────────────
# HRBP/MANAGER VIEWS
# ─────────────────────────────────────────────────────────────────────────────

@permission_required('manage_onboarding_plans')
@require_http_methods(['GET', 'POST'])
def manage_onboarding_plans(request):
    """HRBP/Manager view to create and manage onboarding plans."""
    creator = request.user

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_plan':
            employee_id = request.POST.get('employee_id')
            try:
                employee = User.objects.get(id=employee_id)

                # Only create plan for employees
                if employee.role != 'employee':
                    messages.error(request, 'Can only create plans for employees.')
                    return redirect('manage_onboarding_plans')

                create_plan(employee, creator)
                log_activity(request, action='create_onboarding_plan', entity_type='onboarding_plan',
                            description=f'Created 30/60/90 plan for {employee.full_name}')

                # Send plan assignment email
                if should_send_email(employee, 'stage_updates'):
                    send_onboarding_plan_assigned(employee, creator)

                messages.success(request, f'Onboarding plan created for {employee.full_name}!')

            except User.DoesNotExist:
                messages.error(request, 'Employee not found.')

        elif action == 'post_feedback':
            employee_id = request.POST.get('employee_id')
            phase = request.POST.get('phase')
            message = request.POST.get('message', '').strip()

            if not message:
                messages.error(request, 'Message cannot be empty.')
                return redirect('manage_onboarding_plans')

            try:
                employee = User.objects.get(id=employee_id)
                if post_update(employee, phase, creator, message, author_role=creator.role):
                    log_activity(request, action='post_plan_feedback', entity_type='onboarding_plan',
                                description=f'Posted feedback on {phase} for {employee.full_name}')

                    # Send feedback notification email
                    if should_send_email(employee, 'stage_updates'):
                        send_onboarding_plan_feedback(employee, creator, phase)

                    messages.success(request, 'Feedback posted!')
                else:
                    messages.error(request, 'Could not post feedback.')

            except User.DoesNotExist:
                messages.error(request, 'Employee not found.')

        return redirect('manage_onboarding_plans')

    # Get all employees with plans or without plans
    employees_with_plans = Engagement.objects.filter(
        kind='onboarding_plan'
    ).values_list('user_id', flat=True)

    employees_with_plans_data = []
    for emp_id in employees_with_plans:
        try:
            emp = User.objects.get(id=emp_id)
            progress = get_progress_stats(emp)
            employees_with_plans_data.append({
                'employee': emp,
                'progress': progress,
            })
        except User.DoesNotExist:
            pass

    # Get employees without plans (in onboarding)
    employees_without_plans = User.objects.filter(
        role='employee',
        status__in=['medical_upload', 'pre_onboarding', 'onboarding', 'post_onboarding']
    ).exclude(id__in=employees_with_plans).order_by('-date_of_joining')

    ctx = {
        'employees_with_plans': employees_with_plans_data,
        'employees_without_plans': employees_without_plans,
    }

    return render(request, 'onboarding_plan/manager_plans.html', ctx)


@login_required
@require_http_methods(['GET'])
def employee_plan_detail(request, employee_id):
    """HRBP/Manager view of an employee's 30/60/90 plan."""
    viewer = request.user
    employee = get_object_or_404(User, id=employee_id, role='employee')

    # Check permission
    if viewer.role == 'employee':
        return render(request, '403.html', status=403)

    plan_data = get_plan(employee)
    progress = get_progress_stats(employee)

    ctx = {
        'employee': employee,
        'plan_data': plan_data,
        'progress': progress,
        'phases': {
            'day_30': get_phase_status(employee, 'day_30'),
            'day_60': get_phase_status(employee, 'day_60'),
            'day_90': get_phase_status(employee, 'day_90'),
        },
        'can_edit': viewer.role in ['hrbp', 'manager'],
    }

    return render(request, 'onboarding_plan/plan_detail.html', ctx)


@permission_required('manage_onboarding_plans')
@require_http_methods(['POST'])
def manager_mark_milestone(request, employee_id):
    """Manager/HRBP marking milestone as complete."""
    employee = get_object_or_404(User, id=employee_id, role='employee')
    phase = request.POST.get('phase')
    milestone_index = int(request.POST.get('milestone_index', 0))
    completed = request.POST.get('completed') == 'true'

    if update_milestone(employee, phase, milestone_index, completed):
        log_activity(request, action='update_milestone', entity_type='onboarding_plan',
                    description=f'{request.user.full_name} {"completed" if completed else "uncompleted"} milestone for {employee.full_name}')
        return JsonResponse({'success': True})

    return JsonResponse({'success': False, 'error': 'Could not update milestone'}, status=400)


@permission_required('manage_onboarding_plans')
@require_http_methods(['POST'])
def manager_post_feedback(request, employee_id):
    """Manager/HRBP posting feedback on a phase."""
    employee = get_object_or_404(User, id=employee_id, role='employee')
    phase = request.POST.get('phase')
    message = request.POST.get('message', '').strip()

    if not message:
        return JsonResponse({'success': False, 'error': 'Message cannot be empty'}, status=400)

    if post_update(employee, phase, request.user, message, author_role=request.user.role):
        log_activity(request, action='post_plan_feedback', entity_type='onboarding_plan',
                    description=f'{request.user.full_name} posted feedback on {phase} for {employee.full_name}')

        # Send feedback notification email
        if should_send_email(employee, 'stage_updates'):
            send_onboarding_plan_feedback(employee, request.user, phase)

        return JsonResponse({
            'success': True,
            'post': {
                'author_name': request.user.full_name,
                'author_role': request.user.role,
                'message': message,
                'posted_at': __import__('django.utils.timezone', fromlist=['now']).now().isoformat(),
            }
        })

    return JsonResponse({'success': False, 'error': 'Could not post feedback'}, status=400)
