"""
Analytics dashboard views.

Provides onboarding metrics, funnel analysis, and performance reporting.
"""
from django.shortcuts import render
from django.utils.decorators import decorator_from_middleware
from ..decorators import staff_required, permission_required
from ..services.analytics_service import (
    get_onboarding_funnel,
    get_stage_completion_metrics,
    get_overdue_metrics,
    get_time_to_completion_metrics,
    get_department_breakdown,
    get_summary_stats,
)


@staff_required
def analytics_dashboard(request):
    """
    Analytics dashboard showing onboarding metrics and trends.

    Visible to super_admin, admin, and hrbp roles.
    """
    if not request.user.has_perm_key('view_analytics'):
        return render(request, '403.html', status=403)

    # Gather all analytics data
    summary = get_summary_stats()
    funnel = get_onboarding_funnel()
    completion = get_stage_completion_metrics()
    overdue = get_overdue_metrics()
    time_metrics = get_time_to_completion_metrics()
    departments = get_department_breakdown()

    # Prepare data for charts (JSON-serializable)
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
        # Chart data (JSON)
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
