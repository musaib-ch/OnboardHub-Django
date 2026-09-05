"""
Enterprise onboarding success plan views.
"""
from __future__ import annotations

import json

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from ..decorators import login_required, permission_required
from ..models import Content, Engagement, User
from ..permissions import is_staff_role, role_scope_type
from ..services import log_activity
from ..services.onboarding_plan_service import OnboardingPlanService, SECTION_LIBRARY


def _scoped_employee_qs(viewer, qs):
    scope_type = role_scope_type(viewer.role)
    if scope_type == "department":
        depts = (viewer.scope or {}).get("departments") or []
        return qs.filter(department_id__in=depts) if depts else qs.none()
    if scope_type == "location":
        locs = (viewer.scope or {}).get("locations") or []
        return qs.filter(location_code__in=locs) if locs else qs.none()
    return qs


def _can_view_employee(viewer, employee):
    if viewer.role == "super_admin":
        return True
    if viewer.role == "employee":
        return viewer.id == employee.id
    if not is_staff_role(viewer.role):
        return False
    if role_scope_type(viewer.role) is None:
        return True
    return _scoped_employee_qs(viewer, User.objects.filter(id=employee.id)).exists()


def _parse_payload(request, key="payload_json"):
    raw = request.POST.get(key, "").strip()
    if not raw:
        return {}
    return json.loads(raw)


@login_required
def my_onboarding_plan(request):
    user = request.user
    if user.role != "employee":
        return render(request, "403.html", status=403)
    engagement = OnboardingPlanService.get_plan_record(user)
    if not engagement:
        messages.warning(request, "No onboarding success plan has been assigned to you yet.")
        return redirect("employee_home")
    ctx = OnboardingPlanService.get_plan_context(user)
    return render(request, "onboarding_plan/employee_plan.html", ctx)


@login_required
@require_http_methods(["POST"])
def mark_milestone_complete(request):
    user = request.user
    if user.role != "employee":
        return redirect("index")
    engagement = OnboardingPlanService.get_plan_record(user)
    if not engagement:
        messages.error(request, "No plan found.")
        return redirect("my_onboarding_plan")
    activity_id = request.POST.get("activity_id")
    action = request.POST.get("action") or "mark_complete"
    comment = request.POST.get("comment", "")
    ok, msg = OnboardingPlanService.update_activity(
        engagement, activity_id, user, action, comment=comment, files=request.FILES.getlist("attachments")
    )
    messages.success(request, msg) if ok else messages.error(request, msg)
    return redirect("my_onboarding_plan")


@login_required
@require_http_methods(["POST"])
def post_plan_update(request, phase):
    user = request.user
    if user.role != "employee":
        return redirect("index")
    engagement = OnboardingPlanService.get_plan_record(user)
    if not engagement:
        messages.error(request, "No plan found.")
        return redirect("my_onboarding_plan")
    activity_id = request.POST.get("activity_id")
    message = request.POST.get("message", "").strip()
    if not activity_id or not message:
        messages.error(request, "Message cannot be empty.")
        return redirect("my_onboarding_plan")
    OnboardingPlanService.add_activity_message(user, engagement.id, activity_id, user, message, kind="reply")
    messages.success(request, "Comment posted.")
    return redirect("my_onboarding_plan")


@permission_required("manage_onboarding_plans")
@require_http_methods(["GET", "POST"])
def manage_onboarding_plans(request):
    actor = request.user
    OnboardingPlanService.sync_default_templates(actor=actor)

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "save_template":
                template_id = int(request.POST.get("template_id") or 0) or None
                payload = _parse_payload(request)
                template = OnboardingPlanService.save_template(actor, payload, template_id=template_id)
                log_activity(request, action="save_onboarding_plan_template", entity_type="content", entity_id=template.id, description=f"Saved plan template {template.title}")
                messages.success(request, "Template saved.")
                return redirect(f"{request.path}?template={template.id}")
            if action == "duplicate_template":
                template = OnboardingPlanService.duplicate_template(actor, int(request.POST["template_id"]))
                messages.success(request, "Template duplicated.")
                return redirect(f"{request.path}?template={template.id}")
            if action == "archive_template":
                OnboardingPlanService.archive_template(int(request.POST["template_id"]))
                messages.success(request, "Template archived.")
                return redirect("manage_onboarding_plans")
            if action == "import_templates":
                uploaded = request.FILES.get("import_file")
                count = OnboardingPlanService.import_templates(actor, uploaded)
                messages.success(request, f"Imported {count} template(s).")
                return redirect("manage_onboarding_plans")
            if action == "export_template":
                template_id = int(request.POST["template_id"])
                payload = OnboardingPlanService.export_template_payload(template_id)
                response = HttpResponse(json.dumps(payload, indent=2), content_type="application/json")
                response["Content-Disposition"] = f'attachment; filename="onboarding-plan-template-{template_id}.json"'
                return response
            if action == "assign_template":
                employee = get_object_or_404(User, id=request.POST.get("employee_id"), role="employee")
                if not _can_view_employee(actor, employee):
                    messages.error(request, "This employee is outside your scope.")
                    return redirect("manage_onboarding_plans")
                template = get_object_or_404(Content, id=request.POST.get("template_id"), kind="onboarding_plan")
                OnboardingPlanService.assign_template(employee, template, actor)
                messages.success(request, f"Assigned template to {employee.full_name}.")
                return redirect(f"{request.path}?employee={employee.id}")
            if action == "bulk_assign":
                template = get_object_or_404(Content, id=request.POST.get("template_id"), kind="onboarding_plan")
                employee_ids = [int(x) for x in request.POST.getlist("employee_ids") if x.isdigit()]
                employees = _scoped_employee_qs(actor, User.objects.filter(id__in=employee_ids, role="employee"))
                count = OnboardingPlanService.bulk_assign_template(actor, template, employees)
                messages.success(request, f"Assigned template to {count} employee(s).")
                return redirect("manage_onboarding_plans")
            if action == "create_custom_plan":
                employee = get_object_or_404(User, id=request.POST.get("employee_id"), role="employee")
                if not _can_view_employee(actor, employee):
                    messages.error(request, "This employee is outside your scope.")
                    return redirect("manage_onboarding_plans")
                payload = _parse_payload(request)
                OnboardingPlanService.create_custom_plan(employee, actor, payload)
                messages.success(request, f"Created custom plan for {employee.full_name}.")
                return redirect(f"{request.path}?employee={employee.id}")
        except Exception as exc:
            messages.error(request, f"Could not complete action: {exc}")
            return redirect("manage_onboarding_plans")

    selected_template = None
    template_id = request.GET.get("template")
    if template_id and template_id.isdigit():
        selected_template = get_object_or_404(Content, id=int(template_id), kind="onboarding_plan")

    selected_employee = None
    selected_plan = None
    employee_id = request.GET.get("employee")
    if employee_id and employee_id.isdigit():
        selected_employee = get_object_or_404(User, id=int(employee_id), role="employee")
        if _can_view_employee(actor, selected_employee):
            selected_plan = OnboardingPlanService.get_plan_context(selected_employee)
        else:
            selected_employee = None

    ctx = {
        "templates": OnboardingPlanService.templates_for_ui(actor),
        "selected_template": selected_template,
        "selected_template_json": json.dumps((selected_template.meta or {}) if selected_template else {}, indent=2),
        "employees": OnboardingPlanService.employees_for_assignment(actor),
        "active_plans": OnboardingPlanService.active_plans_for_ui(actor),
        "plan_analytics": OnboardingPlanService.analytics_for_viewer(actor),
        "selected_employee": selected_employee,
        "selected_plan": selected_plan,
        "builder_payload": json.dumps(OnboardingPlanService.export_template_payload(selected_template.id) if selected_template else {
            "title": "Custom Onboarding Success Plan",
            "summary": "",
            "phases": [
                {"id": "day-30", "label": "30 Days", "description": "", "sections": []},
                {"id": "day-60", "label": "60 Days", "description": "", "sections": []},
                {"id": "day-90", "label": "90 Days", "description": "", "sections": []},
            ],
        }, indent=2),
        "section_library_list": SECTION_LIBRARY,
        "section_library": json.dumps(["Company", "HR", "Department", "Systems", "Compliance", "Learning", "Meetings", "Projects", "KPIs", "Performance", "Goals", "Documents", "Custom"]),
        "activity_types": json.dumps(["task", "goal", "meeting", "training", "quiz", "course", "document", "reading", "survey", "project", "observation", "certification", "external_link", "form", "video", "custom"]),
        "owner_options": json.dumps([
            {"value": "employee", "label": "Employee"},
            {"value": "manager", "label": "Manager"},
            {"value": "hr", "label": "HR"},
            {"value": "system", "label": "System"},
        ]),
        "completion_types": json.dumps([
            {"value": "manual", "label": "Manual"},
            {"value": "manager_approval", "label": "Manager Approval"},
            {"value": "automatic", "label": "Automatic"},
        ]),
    }
    return render(request, "onboarding_plan/manager_plans.html", ctx)


@login_required
@require_http_methods(["GET", "POST"])
def employee_plan_detail(request, employee_id):
    viewer = request.user
    employee = get_object_or_404(User, id=employee_id, role="employee")
    if not _can_view_employee(viewer, employee) or viewer.role == "medical_approver":
        return render(request, "403.html", status=403)

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "create_plan":
                payload = _parse_payload(request)
                if payload:
                    OnboardingPlanService.create_custom_plan(employee, viewer, payload)
                else:
                    templates = list(OnboardingPlanService.list_templates(viewer))
                    if templates:
                        OnboardingPlanService.assign_template(employee, templates[0], viewer)
                messages.success(request, "Plan created.")
            elif action == "save_plan_json":
                engagement = OnboardingPlanService.get_plan_record(employee)
                if not engagement:
                    messages.error(request, "No plan found.")
                else:
                    OnboardingPlanService.save_plan_structure(engagement, viewer, _parse_payload(request))
                    messages.success(request, "Plan updated.")
            return redirect("employee_plan_detail", employee_id=employee.id)
        except Exception as exc:
            messages.error(request, f"Could not save plan: {exc}")
            return redirect("employee_plan_detail", employee_id=employee.id)

    ctx = OnboardingPlanService.get_plan_context(employee)
    ctx.update({
        "employee": employee,
        "can_edit": viewer.role != "employee",
        "plan_json": json.dumps(ctx.get("plan_data") or {}, indent=2),
        "activity_types": json.dumps(["task", "goal", "meeting", "training", "quiz", "course", "document", "reading", "survey", "project", "observation", "certification", "external_link", "form", "video", "custom"]),
    })
    return render(request, "onboarding_plan/plan_detail.html", ctx)


@permission_required("manage_onboarding_plans")
@require_http_methods(["POST"])
def manager_mark_milestone(request, employee_id):
    employee = get_object_or_404(User, id=employee_id, role="employee")
    if not _can_view_employee(request.user, employee):
        return JsonResponse({"success": False, "error": "Outside your scope."}, status=403)
    engagement = OnboardingPlanService.get_plan_record(employee)
    if not engagement:
        return JsonResponse({"success": False, "error": "No plan found."}, status=404)
    activity_id = request.POST.get("activity_id")
    action = request.POST.get("action") or "approve"
    comment = request.POST.get("comment", "")
    ok, msg = OnboardingPlanService.update_activity(
        engagement, activity_id, request.user, action, comment=comment, files=request.FILES.getlist("attachments")
    )
    return JsonResponse({"success": ok, "message": msg}, status=200 if ok else 400)


@permission_required("manage_onboarding_plans")
@require_http_methods(["POST"])
def manager_post_feedback(request, employee_id):
    employee = get_object_or_404(User, id=employee_id, role="employee")
    if not _can_view_employee(request.user, employee):
        return JsonResponse({"success": False, "error": "Outside your scope."}, status=403)
    engagement = OnboardingPlanService.get_plan_record(employee)
    if not engagement:
        return JsonResponse({"success": False, "error": "No plan found."}, status=404)
    activity_id = request.POST.get("activity_id")
    message = request.POST.get("message", "").strip()
    if not activity_id or not message:
        return JsonResponse({"success": False, "error": "Message cannot be empty."}, status=400)
    review = OnboardingPlanService.add_activity_message(employee, engagement.id, activity_id, request.user, message, kind="message")
    return JsonResponse({
        "success": True,
        "post": {
            "id": review.id,
            "author_name": request.user.full_name,
            "author_role": request.user.role,
            "message": message,
            "posted_at": review.created_at.isoformat(),
        }
    })
