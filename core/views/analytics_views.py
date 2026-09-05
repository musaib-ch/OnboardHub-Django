"""
Analytics dashboard views.

Provides onboarding metrics, funnel analysis, training analytics, and session analytics.
"""
import csv
from django.shortcuts import render
from django.http import HttpResponse
from django.utils import timezone
from ..decorators import staff_required, permission_required
from ..services.analytics_service import (
    get_onboarding_funnel,
    get_stage_completion_metrics,
    get_overdue_metrics,
    get_time_to_completion_metrics,
    get_department_breakdown,
    get_summary_stats,
    get_training_analytics,
    get_session_analytics,
)
from ..services.onboarding_plan_service import OnboardingPlanService


@staff_required
def analytics_dashboard(request):
    """
    Analytics dashboard showing onboarding metrics and trends.

    Visible to super_admin, admin, and hrbp roles.
    """
    if not request.user.has_perm_key('view_analytics'):
        return render(request, '403.html', status=403)

    summary = get_summary_stats(viewer=request.user)
    funnel = get_onboarding_funnel(viewer=request.user)
    completion = get_stage_completion_metrics(viewer=request.user)
    overdue = get_overdue_metrics(viewer=request.user)
    time_metrics = get_time_to_completion_metrics(viewer=request.user)
    departments = get_department_breakdown(viewer=request.user)
    plan_analytics = OnboardingPlanService.analytics_for_viewer(request.user)

    funnel_labels = [f['label'] for f in funnel.values()]
    funnel_counts = [f['count'] for f in funnel.values()]
    funnel_percentages = [f['percentage'] for f in funnel.values()]

    completion_labels = [v['label'] for v in completion.values()]
    completion_rates = [v['completion_rate'] for v in completion.values()]

    overdue_labels = [v['label'] for v in overdue.values()]
    overdue_counts = [v['overdue'] for v in overdue.values()]
    at_risk_counts = [v['at_risk'] for v in overdue.values()]

    dept_labels = [d['department'] for d in departments]
    dept_rates = [d['completion_rate'] for d in departments]

    ctx = {
        'summary': summary,
        'funnel': funnel,
        'completion': completion,
        'overdue': overdue,
        'time_metrics': time_metrics,
        'departments': departments,
        'plan_analytics': plan_analytics,
        'funnel_labels': funnel_labels,
        'funnel_counts': funnel_counts,
        'funnel_percentages': funnel_percentages,
        'completion_labels': completion_labels,
        'completion_rates': completion_rates,
        'overdue_labels': overdue_labels,
        'overdue_counts': overdue_counts,
        'at_risk_counts': at_risk_counts,
        'dept_labels': dept_labels,
        'dept_rates': dept_rates,
    }

    return render(request, 'admin/analytics_dashboard.html', ctx)


@staff_required
def training_analytics(request):
    """Dedicated training / learning path analytics page."""
    if not request.user.has_perm_key('view_analytics'):
        return render(request, '403.html', status=403)

    data = get_training_analytics(viewer=request.user)
    return render(request, 'admin/analytics_training.html', {'data': data})


@staff_required
def session_analytics(request):
    """Dedicated session / orientation attendance analytics page."""
    if not request.user.has_perm_key('view_analytics'):
        return render(request, '403.html', status=403)

    data = get_session_analytics(viewer=request.user)
    return render(request, 'admin/analytics_sessions.html', {'data': data})


@staff_required
def export_analytics_csv(request, report_type):
    """Download analytics data as CSV. report_type: onboarding | training | sessions | departments"""
    if not request.user.has_perm_key('export_data'):
        return render(request, '403.html', status=403)

    now = timezone.now().strftime('%Y%m%d_%H%M')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="analytics_{report_type}_{now}.csv"'
    writer = csv.writer(response)

    if report_type == 'onboarding':
        writer.writerow(['Stage', 'Employees Reached', 'Percentage', 'Completion Rate', 'Avg Days', 'Overdue', 'At Risk'])
        funnel = get_onboarding_funnel(viewer=request.user)
        completion = get_stage_completion_metrics(viewer=request.user)
        time_metrics = get_time_to_completion_metrics(viewer=request.user)
        overdue = get_overdue_metrics(viewer=request.user)
        for key in funnel:
            writer.writerow([
                funnel[key]['label'],
                funnel[key]['count'],
                f"{funnel[key]['percentage']}%",
                f"{completion.get(key, {}).get('completion_rate', 0)}%",
                time_metrics.get(key, {}).get('avg_days', 0),
                overdue.get(key, {}).get('overdue', 0),
                overdue.get(key, {}).get('at_risk', 0),
            ])

    elif report_type == 'departments':
        writer.writerow(['Department', 'Total Employees', 'Completed', 'Completion Rate'])
        for dept in get_department_breakdown(viewer=request.user):
            writer.writerow([dept['department'], dept['total'], dept['completed'], f"{dept['completion_rate']}%"])

    elif report_type == 'training':
        writer.writerow(['Learning Path', 'Enrollments', 'Completed', 'Overdue', 'Completion Rate', 'Avg Quiz Score'])
        data = get_training_analytics(viewer=request.user)
        for p in data['paths']:
            writer.writerow([
                p['title'], p['enrollments'], p['completed'], p['overdue'],
                f"{p['completion_rate']}%",
                f"{p['avg_quiz_score']}%" if p['avg_quiz_score'] is not None else 'N/A',
            ])

    elif report_type == 'sessions':
        writer.writerow(['Session Type', 'Sessions', 'Registered', 'Attended', 'Attendance Rate'])
        data = get_session_analytics(viewer=request.user)
        for t in data['type_breakdown']:
            writer.writerow([
                t['label'], t['sessions'], t['registered'], t['attended'],
                f"{t['attendance_rate']}%",
            ])

    else:
        writer.writerow(['Unknown report type'])

    return response
