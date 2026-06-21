"""Admin console: dashboard, employees, users, form builder, documents, medical."""
import json
import secrets

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .. import pipeline
from ..decorators import staff_required, permission_required, roles_required
from ..medical_match import medical_applicability
from ..models import (
    User, OrgUnit, AppSetting, Form, FormResponse, OnboardingDocument, MedicalRecord,
    ReviewMessage, Content, Engagement, STATUS_CHOICES,
)
from ..services import log_activity, notify, onboarding_progress_percent
from ..services.stage_service import advance_employee_to_stage, set_stage_due_date_override, get_stage_progress
from ..permissions import (
    PERMISSION_CATEGORIES, ALL_PERMISSIONS,
    all_roles, custom_roles, delete_custom_role, editable_roles,
    is_employee_role, is_staff_role, resolve_role_permissions, role_base,
    role_label, role_permission_map, role_scope_type, set_role_permissions,
    upsert_custom_role,
)

EMPLOYEE_STATUSES = [s for s, _ in STATUS_CHOICES]

# Statuses that mean "an employee has submitted a stage and is awaiting review".
AWAITING_REVIEW = pipeline.SUBMITTED_STATUSES

# Which permission gates reviewing each stage.
STAGE_REVIEW_PERM = {
    "medical": "approve_medical",
    "pre_onboarding": "approve_pre_onboarding",
    "onboarding": "approve_onboarding",
    "post_onboarding": "approve_onboarding",
}


def _can_review(user, status):
    stage = pipeline.stage_of_status(status)
    perm = STAGE_REVIEW_PERM.get(stage)
    return bool(perm) and user.has_perm_key(perm)


# Organization option kinds shown on the setup page + used by the user form.
ORG_KINDS = [
    ("department", "Departments"),
    ("designation", "Designations"),
    ("grade", "Grades"),
    ("location", "Locations"),
    ("payroll", "Payroll"),
    ("employee_type", "Employee Types"),
]


def _org_options():
    """{'grade': [OrgUnit, ...], 'location': [...], ...} of active options."""
    options = {kind: [] for kind, _ in ORG_KINDS}
    for ou in OrgUnit.objects.filter(is_active=True).order_by("kind", "name"):
        options.setdefault(ou.kind, []).append(ou)
    return options


GENDER_CHOICES = [("male", "Male"), ("female", "Female"), ("other", "Other")]


def _employee_role_keys():
    return [r["key"] for r in all_roles() if r["base"] == "employee"]


def _staff_role_keys():
    return [r["key"] for r in all_roles() if r["base"] == "staff"]


def _creatable_roles():
    return [(r["key"], r["label"], r["base"], r["scope_type"])
            for r in all_roles(include_super=False)]


def _role_meta_map():
    return {r["key"]: {"base": r["base"], "scope_type": r["scope_type"]}
            for r in all_roles()}


def scoped_employee_qs(viewer, qs):
    """Restrict an employee queryset to what the viewer is scoped to see.

    Department/location-scoped roles only see employees in their scope.
    """
    scope_type = role_scope_type(viewer.role)
    if scope_type == "department":
        depts = (viewer.scope or {}).get("departments") or []
        return qs.filter(department_id__in=depts) if depts else qs.none()
    if scope_type == "location":
        locs = (viewer.scope or {}).get("locations") or []
        return qs.filter(location_code__in=locs) if locs else qs.none()
    return qs


def can_view_employee(viewer, emp):
    if role_scope_type(viewer.role) is None and is_staff_role(viewer.role):
        return True
    return scoped_employee_qs(viewer, User.objects.filter(pk=emp.pk)).exists()


def _get_employee(user_id):
    return get_object_or_404(User, id=user_id, role__in=_employee_role_keys())


# ── Bulk employee import (CSV) ───────────────────────────────────────────────
IMPORT_COLUMNS = ["full_name", "email", "employee_id", "department", "designation",
                  "grade", "location", "payroll", "employee_type",
                  "date_of_birth", "gender", "date_of_joining"]


def _parse_date(value):
    from datetime import datetime
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


@permission_required("manage_users")
@require_http_methods(["GET", "POST"])
def import_employees(request):
    import csv
    import io
    import secrets

    if request.GET.get("template"):
        from ..exporters import csv_response
        example = ["Jane Doe", "jane.doe@company.com", "EMP-1001", "Engineering",
                   "Software Engineer", "M1", "Lahore", "Monthly", "Permanent",
                   "1995-04-21", "female", "2026-07-01"]
        return csv_response("employee_import_template.csv", IMPORT_COLUMNS, [example])

    if request.method == "POST":
        f = request.FILES.get("file")
        if not f:
            messages.error(request, "Please choose a CSV file.")
            return redirect("admin_import_employees")
        try:
            text = f.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            messages.error(request, "Could not read the file — please upload a UTF-8 CSV.")
            return redirect("admin_import_employees")

        reader = csv.DictReader(io.StringIO(text))
        created, skipped = [], []
        opt_kinds = {"grade": "grade", "location": "location",
                     "payroll": "payroll", "employee_type": "employee_type"}

        for line_no, row in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            email = row.get("email", "").lower()
            name = row.get("full_name", "")
            if not email or not name:
                skipped.append((line_no, email or "(blank)", "missing full_name or email"))
                continue
            if User.objects.filter(email__iexact=email).exists():
                skipped.append((line_no, email, "email already exists"))
                continue

            # Department: match existing or create the option.
            dept = None
            if row.get("department"):
                dept = OrgUnit.objects.filter(kind="department", name__iexact=row["department"]).first()
                if not dept:
                    dept = OrgUnit.objects.create(kind="department", name=row["department"],
                                                  tenant=request.user.tenant)
            # Add any new grade/location/payroll/type values to the catalog.
            for kind, col in opt_kinds.items():
                val = row.get(col)
                if val and not OrgUnit.objects.filter(kind=kind, name__iexact=val).exists():
                    OrgUnit.objects.create(kind=kind, name=val, tenant=request.user.tenant)

            temp = secrets.token_urlsafe(9)
            try:
                user = User(
                    email=email, full_name=name, role="employee", status="pending",
                    must_change_password=True, tenant=request.user.tenant, created_by=request.user,
                    employee_id=row.get("employee_id") or None,
                    position_title=row.get("designation") or None,
                    grade=row.get("grade") or None,
                    location_code=row.get("location") or None,
                    payroll=row.get("payroll") or None,
                    employee_type=row.get("employee_type") or None,
                    gender=(row.get("gender") or "").lower() or None,
                    department=dept,
                    date_of_birth=_parse_date(row.get("date_of_birth")),
                    date_of_joining=_parse_date(row.get("date_of_joining")),
                )
                user.set_password(temp)
                user.save()
            except Exception as exc:  # noqa: BLE001
                skipped.append((line_no, email, str(exc)[:120]))
                continue
            created.append({"email": email, "name": name, "password": temp})

        log_activity(request, action="import_employees", entity_type="employee",
                     description=f"Imported {len(created)} employees ({len(skipped)} skipped)")
        messages.success(request, f"Import finished: {len(created)} created, {len(skipped)} skipped.")
        return render(request, "admin/import_employees.html",
                      {"created": created, "skipped": skipped, "done": True,
                       "columns": IMPORT_COLUMNS})

    return render(request, "admin/import_employees.html", {"columns": IMPORT_COLUMNS})


# ── Exports (reusable CSV) ───────────────────────────────────────────────────
@permission_required("export_data")
def export_employees(request):
    from ..exporters import csv_response, EMPLOYEE_HEADER, employee_rows
    qs = scoped_employee_qs(request.user, User.objects.filter(role__in=_employee_role_keys())).exclude(status="deleted")
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(email__icontains=q) | Q(employee_id__icontains=q))
    if status:
        qs = qs.filter(status=status)
    log_activity(request, action="export_employees", entity_type="employee",
                 description=f"Exported {qs.count()} employees")
    return csv_response("employees.csv", EMPLOYEE_HEADER, employee_rows(qs.order_by("full_name")))


@permission_required("export_data")
def export_users(request):
    from ..exporters import csv_response, USER_HEADER, user_rows
    qs = User.objects.exclude(role__in=_employee_role_keys()).exclude(status="deleted").order_by("full_name")
    return csv_response("users.csv", USER_HEADER, user_rows(qs))


@permission_required("export_data")
def export_employee_detail(request, user_id):
    from ..exporters import csv_response, EMPLOYEE_DETAIL_HEADER, employee_detail_rows
    emp = _get_employee(user_id)
    if not can_view_employee(request.user, emp):
        messages.error(request, "This employee is outside your scope.")
        return redirect("admin_employees")
    log_activity(request, action="export_employee_detail", entity_type="employee",
                 entity_id=emp.id, description=f"Exported onboarding data for {emp.email}")
    fname = f"employee_{emp.employee_id or emp.id}_onboarding.csv"
    return csv_response(fname, EMPLOYEE_DETAIL_HEADER, employee_detail_rows(emp))


@permission_required("manage_forms")
def export_form_responses_view(request, form_id):
    from ..exporters import csv_response, export_form_responses
    form = get_object_or_404(Form, id=form_id)
    header, rows = export_form_responses(form)
    safe = "".join(c for c in form.name if c.isalnum() or c in " -_").strip().replace(" ", "_")
    return csv_response(f"{safe or 'form'}_responses.csv", header, rows)


@staff_required
def dashboard(request):
    employees = scoped_employee_qs(request.user, User.objects.filter(role__in=_employee_role_keys()))
    today = timezone.now().date()
    in_10_days = today + timezone.timedelta(days=10)
    joining_soon = employees.filter(date_of_joining__gte=today, date_of_joining__lte=in_10_days).count()

    # Determine user role for role-specific dashboard
    is_super_admin = request.user.role == "super_admin"
    is_admin = request.user.role == "admin"
    is_medical_approver = request.user.role == "medical_approver"
    is_hrbp = request.user.role == "hrbp"

    # Count overdue employees (current stage due date passed)
    now = timezone.now()
    overdue_employees = employees.exclude(status="completed").filter(
        stage_due_date__isnull=False,
        stage_due_date__lt=now
    ).count()

    stats = {
        "total": employees.count(),
        "pending": employees.filter(status="pending").count(),
        "in_progress": employees.exclude(status__in=["completed", "pending", "deleted"]).count(),
        "completed": employees.filter(status="completed").count(),
        "on_hold": employees.filter(status="on_hold").count(),
        "awaiting_review": employees.filter(status__in=AWAITING_REVIEW).count(),
        "joining_soon": joining_soon,
        "overdue": overdue_employees,
    }
    recent = employees.exclude(status="deleted").order_by("-created_at")[:8]
    review_queue = employees.filter(status__in=AWAITING_REVIEW).order_by("-updated_at")[:8]

    path_enrollments = Engagement.objects.filter(kind="enrollment", content__kind="learning_path")
    learning_stats = {
        "paths": Content.objects.filter(kind="learning_path", is_active=True).count(),
        "active": path_enrollments.exclude(status="completed").count(),
        "completed": path_enrollments.filter(status="completed").count(),
        "overdue": path_enrollments.exclude(status="completed").filter(
            due_date__lt=timezone.now().date()).count(),
    }
    medical_review_queue = [e for e in employees.filter(status__in=pipeline.SUBMITTED_STATUSES).order_by("-updated_at")
                            if pipeline.stage_of_status(e.status) == "medical"]
    can_medical_review = request.user.has_perm_key("medical_review") or request.user.has_perm_key("approve_medical")

    # Dashboard visibility control
    show_medical_tiles = is_super_admin or can_medical_review
    show_people_tiles = (is_super_admin or is_admin or is_hrbp) and request.user.has_perm_key("view_employees")
    show_learning_tiles = (is_super_admin or is_admin) and (request.user.has_perm_key("view_training") or request.user.has_perm_key("view_programs"))

    # Medical approvers only see medical content; no other tiles
    if is_medical_approver:
        show_people_tiles = False
        show_learning_tiles = False
        recent = employees.exclude(status="deleted").order_by("-updated_at")[:8]

    # HRBP sees joining_soon tile if > 0, but table shows stage tracking
    dashboard_review_queue = medical_review_queue if can_medical_review else review_queue
    dashboard_review_title = "Medical Submissions Awaiting Review" if can_medical_review else "Awaiting Your Review"

    return render(request, "admin/dashboard.html", {
        "stats": stats, "recent": recent, "review_queue": review_queue,
        "learning_stats": learning_stats,
        "can_approve_medical": request.user.has_perm_key("approve_medical"),
        "can_medical_review": can_medical_review,
        "medical_review_queue": medical_review_queue,
        "medical_review_count": len(medical_review_queue),
        "dashboard_review_queue": dashboard_review_queue if can_medical_review else [],
        "dashboard_review_title": dashboard_review_title,
        "show_people_tiles": show_people_tiles,
        "show_learning_tiles": show_learning_tiles,
        "show_medical_tiles": show_medical_tiles,
        "is_medical_approver": is_medical_approver,
        "is_hrbp": is_hrbp,
        "is_super_admin": is_super_admin,
        "is_admin": is_admin,
    })


@staff_required
def employees(request):
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    qs = scoped_employee_qs(request.user, User.objects.filter(role__in=_employee_role_keys())).exclude(status="deleted")
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(email__icontains=q)
                       | Q(employee_id__icontains=q))
    if status:
        qs = qs.filter(status=status)
    qs = qs.order_by("-created_at")
    return render(request, "admin/employees.html", {
        "employees": qs, "q": q, "status": status, "statuses": EMPLOYEE_STATUSES,
    })


# Where the employee should be sent to act on each review outcome.
STAGE_LINK = {
    "medical": "/employee/medical/",
    "pre_onboarding": "/employee/pre-onboarding/",
    "onboarding": "/employee/onboarding/",
    "post_onboarding": "/employee/post-onboarding/",
}


@staff_required
@require_http_methods(["GET", "POST"])
def employee_detail(request, user_id):
    emp = _get_employee(user_id)
    if not can_view_employee(request.user, emp):
        messages.error(request, "This employee is outside your assigned scope.")
        return redirect("admin_employees")
    if request.user.role == "medical_approver":
        return redirect(f"{reverse('admin_medical_review')}?user_id={emp.id}&has_submissions=1")

    # Handle workflow update
    if request.method == "POST" and request.POST.get("action") == "update_workflow":
        from ..pipeline_v2 import create_employee_stage_path
        new_stages = request.POST.getlist("workflow_stages")
        change_reason = request.POST.get("workflow_change_reason", "Manual update from employee profile")
        if new_stages:
            create_employee_stage_path(emp, new_stages, change_reason=change_reason)
            log_activity(request, action="update_employee_workflow", entity_type="employee", entity_id=emp.id,
                        description=f"Updated workflow to {', '.join(new_stages)}")
            messages.success(request, "Workflow updated successfully.")

    responses = FormResponse.objects.filter(employee=emp).select_related("form")
    medical = MedicalRecord.objects.filter(employee=emp)
    actions = pipeline.review_actions_for(emp.status)
    review_stage = pipeline.stage_of_status(emp.status)
    convo_stage = pipeline.current_stage(emp) or review_stage
    thread = ReviewMessage.objects.filter(employee=emp, stage=convo_stage).select_related("author")
    # Email/message templates, pre-resolved with this employee's real values so the
    # admin can drop one into the conversation box (see Phase 4 — sendable templates).
    from ..email_service import all_email_templates, render_email, employee_email_context
    ctx_tags = employee_email_context(emp, link="/employee/home/")
    msg_templates = []
    for t in all_email_templates():
        subject, body = render_email(t["key"], ctx_tags)
        msg_templates.append({"key": t["key"], "label": t["label"],
                              "subject": subject, "body": body})

    # Phase 1: Progress visualization data
    from ..models import AppSetting
    import json
    stages_json = AppSetting.get('stages', '{}')
    stages_dict = json.loads(stages_json) if isinstance(stages_json, str) else stages_json

    # Convert stage config to list format for template
    stage_list = []
    for key in ['medical', 'pre_onboarding', 'onboarding', 'post_onboarding']:
        config = stages_dict.get(key, {})
        stage_list.append({
            'stage_key': key,
            'label': config.get('label', key.replace('_', ' ').title()),
            'order': config.get('order', 0),
            'is_enabled': config.get('is_enabled', True),
        })
    stages = sorted(stage_list, key=lambda s: s['order'])
    current_stage_key = pipeline.stage_of_status(emp.status)

    # Calculate status for each stage
    completed_statuses = {'pre_onboarding', 'pre_onboarding_submitted', 'pre_onboarding_resubmission',
                         'pre_onboarding_info_requested', 'pre_onboarding_rejected',
                         'onboarding', 'post_onboarding', 'completed'}
    stage_statuses = {}
    for stage in stages:
        if emp.status == 'completed':
            stage_statuses[stage['stage_key']] = 'completed'
        elif stage['stage_key'] == current_stage_key:
            stage_statuses[stage['stage_key']] = emp.stage_status()  # pending, in_progress, overdue
        elif stage['stage_key'] in completed_statuses and emp.status in completed_statuses:
            # Check if this stage comes before current stage
            stage_order = {s['stage_key']: s['order'] for s in stages}
            if stage_order.get(stage['stage_key'], 0) < stage_order.get(current_stage_key, 999):
                stage_statuses[stage['stage_key']] = 'completed'
            else:
                stage_statuses[stage['stage_key']] = 'pending'
        else:
            stage_statuses[stage['stage_key']] = 'pending'

    stage_progress = {
        'status': emp.stage_status(),
        'days_remaining': emp.days_remaining_in_stage(),
        'due_date': emp.get_effective_due_date(),
        'entered_at': emp.stage_entered_at,
        'is_overdue': emp.is_stage_overdue(),
        'stage_name': pipeline.STAGE_LABELS.get(current_stage_key, current_stage_key),
    }

    # Add stage statuses to stages for template
    for stage in stages:
        stage['status'] = stage_statuses.get(stage['stage_key'], 'pending')

    # Get unified stages with all activities
    from ..services.unified_stages_service import get_employee_all_stages
    unified_stages = get_employee_all_stages(emp)

    # Get employee's custom workflow path
    from ..pipeline_v2 import get_employee_stage_path
    from ..models import StageDefinition
    employee_stage_path = get_employee_stage_path(emp)
    stage_definitions = {s.stage_key: s for s in StageDefinition.objects.all()}

    return render(request, "admin/employee_detail.html", {
        "emp": emp,
        "msg_templates": msg_templates,
        "responses": responses,
        "medical": medical,
        "pct": onboarding_progress_percent(emp.status, emp),
        "statuses": EMPLOYEE_STATUSES,
        "review_actions": actions,
        "review_stage_label": pipeline.STAGE_LABELS.get(review_stage, ""),
        "awaiting_review": bool(actions),
        "can_review": _can_review(request.user, emp.status),
        "can_bypass": request.user.has_perm_key("bypass_stages"),
        "stages": stages,
        "stage_progress": stage_progress,
        "medical_status": stage_statuses.get('medical_upload', 'pending'),
        "pre_onboarding_status": stage_statuses.get('pre_onboarding', 'pending'),
        "onboarding_status": stage_statuses.get('onboarding', 'pending'),
        "post_onboarding_status": stage_statuses.get('post_onboarding', 'pending'),
        "can_on_behalf": request.user.has_perm_key("on_behalf_documents"),
        "current_stage_label": pipeline.STAGE_LABELS.get(pipeline.current_stage(emp), ""),
        "is_onboarding_active": pipeline.current_stage(emp) is not None
                                and emp.status not in ("deleted", "on_hold"),
        # Workflow configuration
        "employee_stage_path": employee_stage_path,
        "stage_definitions": stage_definitions,
        "has_custom_path": emp.stage_path is not None,
        "thread": thread,
        "convo_stage": convo_stage,
        "convo_stage_label": pipeline.STAGE_LABELS.get(convo_stage, ""),
        "unified_stages": unified_stages,  # All stages with activities
        "is_super_admin": request.user.role == 'super_admin',
    })


@staff_required
@require_http_methods(["POST"])
def delete_employee(request, user_id):
    """Soft delete an employee by marking status as 'deleted'."""
    emp = _get_employee(user_id)
    if not can_view_employee(request.user, emp):
        messages.error(request, "This employee is outside your assigned scope.")
        return redirect("admin_employees")

    # Soft delete - set status to deleted
    old_status = emp.status
    emp.status = "deleted"
    emp.save(update_fields=["status"])

    log_activity(request, action="delete_employee", entity_type="employee", entity_id=emp.id,
                 description=f"Marked {emp.email} as deleted (was {old_status})")

    messages.success(request, f"✓ {emp.full_name} has been deleted (marked as inactive).")
    return redirect("admin_employees")


@permission_required("approve_medical")
@require_http_methods(["GET", "POST"])
def medical_review(request):
    """Approver UI: pick an employee and review their uploaded medical records."""
    qs = scoped_employee_qs(request.user, User.objects.filter(role__in=_employee_role_keys())).exclude(status="deleted").order_by("full_name")
    # Optional filter: only show employees who have uploaded medical files.
    if request.GET.get('has_submissions'):
        qs = qs.filter(medical_records__file__isnull=False).distinct()
    user_id = request.GET.get("user_id")
    selected = None
    records = []
    if user_id:
        try:
            selected = _get_employee(int(user_id))
        except Exception:
            selected = None
        if selected and not can_view_employee(request.user, selected):
            messages.error(request, "That employee is outside your scope.")
            return redirect("admin_medical_review")
        if selected:
            records = list(MedicalRecord.objects.filter(employee=selected).order_by("requirement_name"))

    if request.method == "POST" and selected:
        action = request.POST.get("action")
        record_id = request.POST.get("record_id")
        note = (request.POST.get("note") or "").strip()
        keep_filter = request.POST.get("has_submissions")
        now = timezone.now()

        if action == "approve_all":
            recs = MedicalRecord.objects.filter(employee=selected, is_catalog=False)
            recs.update(status="approved", reviewed_by=request.user, reviewed_at=now)
            log_activity(request, action="approve_medical", entity_type="employee", entity_id=selected.id,
                         description=f"Approved all medical records for {selected.email}")
            messages.success(request, f"Approved all medical documents for {selected.full_name}.")
            _advance_medical_if_ready(request, selected)

        elif action == "reject_all":
            recs = MedicalRecord.objects.filter(employee=selected, is_catalog=False, status__in=["submitted", "info_requested", "changes_requested"])
            recs.update(status="rejected", reviewed_by=request.user, reviewed_at=now)
            log_activity(request, action="reject_medical", entity_type="employee", entity_id=selected.id,
                         description=f"Rejected all medical records for {selected.email}")
            messages.success(request, f"Rejected all pending medical documents for {selected.full_name}.")

        else:
            rec = get_object_or_404(MedicalRecord, id=record_id, employee=selected, is_catalog=False)

            if action == "approve_record":
                rec.status = "approved"
                rec.reviewed_by = request.user
                rec.reviewed_at = now
                rec.save(update_fields=["status", "reviewed_by", "reviewed_at"])
                log_activity(request, action="approve_medical", entity_type="employee", entity_id=selected.id,
                             description=f"Approved medical record '{rec.requirement_name}' for {selected.email}")
                messages.success(request, f"Approved '{rec.requirement_name}'.")
                _advance_medical_if_ready(request, selected)

            elif action == "request_resubmission_record":
                rec.status = "changes_requested"
                rec.reviewed_by = request.user
                rec.reviewed_at = now
                rec.save(update_fields=["status", "reviewed_by", "reviewed_at"])
                ReviewMessage.objects.create(employee=selected, stage="medical", author=request.user,
                                             medical_record=rec, message=note or "Please resubmit the document.", kind="changes")
                notify(selected, f"Resubmission requested: {rec.requirement_name}",
                       note or "Please resubmit the document.", link="/employee/medical/", category="warning")
                log_activity(request, action="request_medical_resubmission", entity_type="employee", entity_id=selected.id,
                             description=f"Requested resubmission for '{rec.requirement_name}' for {selected.email}")
                messages.success(request, f"Requested resubmission for '{rec.requirement_name}'.")

            elif action == "request_info_record":
                rec.status = "info_requested"
                rec.reviewed_by = request.user
                rec.reviewed_at = now
                rec.save(update_fields=["status", "reviewed_by", "reviewed_at"])
                ReviewMessage.objects.create(employee=selected, stage="medical", author=request.user,
                                             medical_record=rec, message=note or "Please provide additional information.", kind="info_request")
                notify(selected, f"Additional information requested: {rec.requirement_name}",
                       note or "Please provide additional information.", link="/employee/medical/", category="info")
                log_activity(request, action="request_medical_info", entity_type="employee", entity_id=selected.id,
                             description=f"Requested additional info for '{rec.requirement_name}' for {selected.email}")
                messages.success(request, f"Requested additional information for '{rec.requirement_name}'.")

            elif action == "reject_record":
                rec.status = "rejected"
                rec.reviewed_by = request.user
                rec.reviewed_at = now
                rec.save(update_fields=["status", "reviewed_by", "reviewed_at"])
                ReviewMessage.objects.create(employee=selected, stage="medical", author=request.user,
                                             medical_record=rec, message=note or "Medical document rejected.", kind="rejection")
                notify(selected, f"Medical document rejected: {rec.requirement_name}",
                       note or "Please contact HR.", link="/employee/medical/", category="danger")
                log_activity(request, action="reject_medical", entity_type="employee", entity_id=selected.id,
                             description=f"Rejected '{rec.requirement_name}' for {selected.email}")
                messages.success(request, f"Rejected '{rec.requirement_name}'.")

        query = [f"user_id={selected.id}"]
        if keep_filter:
            query.insert(0, "has_submissions=1")
        return redirect(f"{request.path}?{'&'.join(query)}")

    return render(request, "admin/medical_review.html", {
        "employees": qs,
        "selected": selected,
        "records": records,
    })


@permission_required("approve_medical")
@require_http_methods(["GET"])
def export_medical_documents(request):
    """Export medical documents as ZIP file organized by employee."""
    import zipfile
    import io
    from datetime import datetime

    mode = request.GET.get("mode", "selected")
    emp_ids = request.GET.get("emp_ids", "").split(",") if request.GET.get("emp_ids") else []

    # Build queryset
    qs = scoped_employee_qs(request.user, User.objects.filter(role__in=_employee_role_keys())).exclude(status="deleted")
    if mode == "selected" and emp_ids:
        qs = qs.filter(id__in=[int(eid) for eid in emp_ids if eid])

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for emp in qs:
            records = MedicalRecord.objects.filter(employee=emp, is_catalog=False, file__isnull=False)
            if not records.exists():
                continue

            for rec in records:
                if rec.file:
                    # Build folder structure: Employee Name/document_name.ext
                    file_name = rec.file.name.split('/')[-1]  # Get filename from path
                    arc_name = f"{emp.full_name}/{rec.requirement_name}_{file_name}"

                    # Read and add to ZIP
                    try:
                        rec.file.open('rb')
                        zip_file.writestr(arc_name, rec.file.read())
                        rec.file.close()
                    except Exception:
                        pass

    zip_buffer.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"medical_documents_{timestamp}.zip"

    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@permission_required("on_behalf_documents")
@require_http_methods(["POST"])
def upload_on_behalf(request, user_id):
    emp = _get_employee(user_id)
    if not can_view_employee(request.user, emp):
        messages.error(request, "That employee is outside your scope.")
        return redirect("admin_employees")
    upload = request.FILES.get("file")
    if not upload:
        messages.error(request, "Please choose a file to upload.")
        return redirect("admin_employee_detail", user_id=emp.id)
    target = request.POST.get("requirement") or "new"
    if target != "new":
        rec = get_object_or_404(MedicalRecord, id=target, employee=emp, is_catalog=False)
    else:
        name = (request.POST.get("custom_name") or "").strip() or upload.name
        rec = MedicalRecord(employee=emp, requirement_name=name, is_required=False,
                            tenant=emp.tenant)
    rec.file = upload
    if request.POST.get("approved"):
        rec.status = "approved"
        rec.reviewed_by = request.user
        rec.reviewed_at = timezone.now()
    else:
        rec.status = "uploaded"
    rec.save()
    notify(emp, "A document was uploaded on your behalf", rec.requirement_name,
           link="/employee/medical/", category="info")
    log_activity(request, action="upload_on_behalf", entity_type="employee", entity_id=emp.id,
                 description=f"Uploaded '{rec.requirement_name}' on behalf of {emp.email}")
    messages.success(request, f"Uploaded '{rec.requirement_name}' on behalf of {emp.full_name}.")
    return redirect("admin_employee_detail", user_id=emp.id)


@staff_required
@require_http_methods(["POST"])
def message_employee(request, user_id):
    emp = _get_employee(user_id)
    text = (request.POST.get("message") or "").strip()
    stage = pipeline.current_stage(emp) or pipeline.stage_of_status(emp.status) or "general"
    if not text:
        messages.error(request, "Message can't be empty.")
        return redirect("admin_employee_detail", user_id=emp.id)
    ReviewMessage.objects.create(employee=emp, stage=stage, author=request.user,
                                 message=text, kind="message")
    notify(emp, "New message from your reviewer", text,
           link=STAGE_LINK.get(stage, "/employee/home/"), category="info")
    log_activity(request, action="review_message", entity_type="employee", entity_id=emp.id,
                 description=f"Messaged {emp.email} on {stage}")
    messages.success(request, "Message sent.")
    return redirect("admin_employee_detail", user_id=emp.id)


@staff_required
@require_http_methods(["POST"])
def review_employee(request, user_id):
    emp = _get_employee(user_id)
    action = request.POST.get("action", "")
    note = (request.POST.get("note") or "").strip()

    if not _can_review(request.user, emp.status):
        messages.error(request, "You don't have permission to review this stage.")
        return redirect("admin_employee_detail", user_id=emp.id)

    allowed = pipeline.review_actions_for(emp.status)
    if action not in allowed:
        messages.error(request, "That review action isn't available for this employee's current stage.")
        return redirect("admin_employee_detail", user_id=emp.id)

    stage = pipeline.stage_of_status(emp.status)
    new_status, verb = allowed[action]
    if action == "approve":
        new_status = pipeline.next_status_after(stage)
    old_status = emp.status

    # Use stage_service to advance employee (auto-calculates due dates)
    if action == "approve":
        advance_employee_to_stage(emp, new_status)
    else:
        emp.status = new_status
        emp.save(update_fields=["status"])
    if action == "approve" and stage == "medical":
        _approve_medical_records(emp)

    advanced = action == "approve"
    if advanced and new_status == "completed":
        verb = "approved — onboarding complete"

    title = f"Your {pipeline.STAGE_LABELS.get(stage, 'submission')} was {verb}"
    body = note or f"An administrator {verb} your {stage.replace('_', ' ')} submission."
    notify(emp, title, body, link=STAGE_LINK.get(stage, "/employee/home/"),
           category="success" if advanced else "warning")

    # Record the decision in the conversation thread (so the employee can reply
    # to info/changes requests).
    kind_map = {"request_info": "info_request", "request_changes": "changes",
                "reject": "rejection", "approve": "message"}
    if note or action != "approve":
        ReviewMessage.objects.create(
            employee=emp, stage=stage, author=request.user,
            message=note or f"Submission {verb}.", kind=kind_map.get(action, "message"),
        )

    log_activity(request, action=f"review_{action}", entity_type="employee", entity_id=emp.id,
                 description=f"{old_status} -> {new_status} for {emp.email}"
                             + (f" — note: {note}" if note else ""))
    messages.success(request, f"{pipeline.STAGE_LABELS.get(stage, 'Submission')} {verb}.")
    return redirect("admin_employee_detail", user_id=emp.id)


# ── Users (admins + employees creation) ──────────────────────────────────────
@permission_required("manage_users")
def users(request):
    staff = User.objects.filter(role__in=_staff_role_keys()).exclude(status="deleted").order_by("full_name")
    return render(request, "admin/users.html", {"users": staff, "roles": [(r["key"], r["label"]) for r in all_roles()]})


def _apply_user_fields(request, user):
    """Copy the shared scalar/dropdown fields from POST onto a user."""
    user.full_name = (request.POST.get("full_name") or user.full_name).strip()
    user.phone_number = (request.POST.get("phone_number") or "").strip() or None
    user.position_title = (request.POST.get("position_title") or "").strip() or None
    user.employee_type = (request.POST.get("employee_type") or "").strip() or None
    user.grade = (request.POST.get("grade") or "").strip() or None
    user.location_code = (request.POST.get("location_code") or "").strip() or None
    user.payroll = (request.POST.get("payroll") or "").strip() or None
    user.date_of_birth = (request.POST.get("date_of_birth") or None)
    user.gender = (request.POST.get("gender") or "").strip() or None
    dept_id = request.POST.get("department") or None
    user.department_id = int(dept_id) if dept_id else None
    user.enable_email_notifications = bool(request.POST.get("enable_email_notifications"))
    user.enable_in_app_notifications = bool(request.POST.get("enable_in_app_notifications"))
    user.quiz_access_only = bool(request.POST.get("quiz_access_only")) and is_employee_role(user.role)
    scope = {}
    scope_type = role_scope_type(user.role)
    if scope_type == "department":
        scope["departments"] = [int(x) for x in request.POST.getlist("scope_departments") if x.isdigit()]
    elif scope_type == "location":
        scope["locations"] = [x for x in request.POST.getlist("scope_locations") if x]
    user.scope = scope


def _apply_permissions(request, user):
    """Store only the deviations from the role default in permissions_override."""
    if "permissions" not in request.POST:
        return
    chosen = set(request.POST.getlist("permissions"))
    defaults = resolve_role_permissions(user.role)
    overrides = {}
    for perm in ALL_PERMISSIONS:
        in_default = perm in defaults
        in_chosen = perm in chosen
        if in_chosen != in_default:
            overrides[perm] = in_chosen
    user.permissions_override = overrides


def _apply_employee_workflow(request, user):
    """Create custom stage path for employee based on workflow selection."""
    from .pipeline_v2 import create_employee_stage_path, get_template

    workflow_choice = request.POST.get("workflow_choice", "default")

    if workflow_choice == "template":
        template_name = request.POST.get("template_name")
        template = get_template(template_name) if template_name else None
        if template:
            create_employee_stage_path(
                user,
                stages=template.stages,
                change_reason=f"Created with template: {template.name}"
            )
    elif workflow_choice == "custom":
        custom_stages = request.POST.getlist("custom_stages")
        if custom_stages:
            create_employee_stage_path(
                user,
                stages=custom_stages,
                change_reason="Created with custom stage selection"
            )
    # else: "default" or not specified - leave stage_path as NULL (uses global defaults)


def _user_form_context(selected_perms=None, **extra):
    from .models import StageDefinition, StageTemplate
    from .pipeline_v2 import get_global_default_stages

    ctx = {
        "roles": _creatable_roles(),
        "role_meta": _role_meta_map(),
        "genders": GENDER_CHOICES,
        "org": _org_options(),
        "statuses": EMPLOYEE_STATUSES,
        "permission_categories": PERMISSION_CATEGORIES,
        "role_perms_map": role_permission_map(),
        "selected_perms": selected_perms or set(),
        # Workflow system
        "stage_templates": StageTemplate.objects.filter(is_active=True, is_global=True).values("name", "description", "stages"),
        "all_stages": StageDefinition.objects.filter(is_enabled=True).order_by("order").values("stage_key", "label", "description"),
        "default_stages": get_global_default_stages(),
    }
    ctx.update(extra)
    return ctx


@permission_required("manage_users")
@require_http_methods(["GET", "POST"])
def create_user(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        full_name = (request.POST.get("full_name") or "").strip()
        role = request.POST.get("role") or "employee"
        valid_roles = {r["key"] for r in all_roles(include_super=False)}
        if role == "super_admin" or role not in valid_roles:
            messages.error(request, "Super Admin cannot be created from this page.")
            return redirect("admin_create_user")
        if not email or not full_name:
            messages.error(request, "Full name and email are required.")
            return redirect("admin_create_user")
        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, "A user with that email already exists.")
            return redirect("admin_create_user")
        temp_password = secrets.token_urlsafe(9)
        user = User(
            email=email, role=role,
            employee_id=(request.POST.get("employee_id") or "").strip() or None,
            status="pending" if is_employee_role(role) else "completed",
            must_change_password=True,
            tenant=request.user.tenant,
            created_by=request.user,
        )
        _apply_user_fields(request, user)
        user.set_password(temp_password)
        user.save()
        _apply_permissions(request, user)
        user.save(update_fields=["permissions_override"])

        # Create custom stage path if employee and workflow selected
        if is_employee_role(role):
            _apply_employee_workflow(request, user)

        log_activity(request, action="create_user", entity_type="user", entity_id=user.id,
                     description=f"Created {role} {user.email}")
        messages.success(request, f"User created. Temporary password for {email}: {temp_password}")
        return redirect("admin_edit_user", user_id=user.id)
    return render(request, "admin/create_user.html",
                  _user_form_context(selected_perms=resolve_role_permissions("admin")))


@permission_required("manage_users")
@require_http_methods(["GET", "POST"])
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        new_role = request.POST.get("role") or user.role
        valid_roles = {r["key"] for r in all_roles(include_super=True)}
        if new_role != "super_admin" and new_role in valid_roles:
            user.role = new_role
        _apply_user_fields(request, user)
        new_status = request.POST.get("status")
        if new_status and new_status in EMPLOYEE_STATUSES:
            user.status = new_status
        _apply_permissions(request, user)
        user.save()
        if request.POST.get("reset_password"):
            temp = secrets.token_urlsafe(9)
            user.set_password(temp)
            user.must_change_password = True
            user.save()
            messages.info(request, f"New temporary password: {temp}")
        log_activity(request, action="edit_user", entity_type="user", entity_id=user.id,
                     description=f"Updated {user.email}")
        messages.success(request, "User updated.")
        return redirect("admin_edit_user", user_id=user.id)
    return render(request, "admin/edit_user.html",
                  _user_form_context(edit_user=user,
                                     selected_perms=set(user.effective_permissions())))


def _complete_stage_on_behalf(user, stage):
    """Mark a stage's required items as done on the employee's behalf."""
    if stage == "medical":
        _approve_medical_records(user)
    else:
        for d in OnboardingDocument.objects.filter(stage=stage, is_active=True):
            if not d.signed_by(user.id):
                d.signatures.append({
                    "employee_id": user.id,
                    "signed_at": timezone.now().isoformat(),
                    "on_behalf": True,
                })
                d.save(update_fields=["signatures"])


def _approve_medical_records(user):
    """Materialize applicable requirements and mark medical clearance complete."""
    existing = {r.requirement_name: r for r in MedicalRecord.objects.filter(employee=user)}
    now = timezone.now()
    for c in MedicalRecord.objects.filter(is_catalog=True, is_active=True):
        applies, required, _note = medical_applicability(user, c.meta)
        if not applies:
            continue
        rec = existing.get(c.requirement_name)
        if rec is None:
            MedicalRecord.objects.create(
                employee=user,
                requirement_name=c.requirement_name,
                description=c.description,
                is_required=required,
                is_catalog=False,
                meta=c.meta,
                status="approved",
                reviewed_at=now,
                tenant=user.tenant,
            )
        else:
            rec.description = c.description
            rec.is_required = required
            rec.meta = c.meta
            rec.status = "approved"
            rec.reviewed_at = now
            rec.save(update_fields=[
                "description", "is_required", "meta", "status", "reviewed_at",
            ])


def _advance_medical_if_ready(request, user):
    """Advance an employee out of medical when all required docs are approved."""
    stage = pipeline.stage_of_status(user.status) or "medical"
    if stage != "medical":
        return
    if MedicalRecord.objects.filter(employee=user, is_required=True).exclude(status="approved").exists():
        return
    old_status = user.status
    user.status = pipeline.next_status_after(stage)
    user.save(update_fields=["status"])
    _approve_medical_records(user)
    notify(user, f"{pipeline.STAGE_LABELS.get(stage, 'Medical')} approved",
           "All required medical documents have been approved.",
           link=STAGE_LINK.get(stage, "/employee/home/"), category="success")
    log_activity(request, action="approve_medical_stage", entity_type="employee", entity_id=user.id,
                 description=f"Advanced employee from {old_status} -> {user.status} after approving medical records for {user.email}")
    messages.success(request, "All required medical documents approved — employee advanced.")


@permission_required("bypass_stages")
@require_http_methods(["POST"])
def bypass_stage(request, user_id):
    emp = _get_employee(user_id)
    stage = pipeline.current_stage(emp)
    if not stage:
        messages.info(request, "This employee has already completed onboarding.")
        return redirect("admin_employee_detail", user_id=emp.id)
    _complete_stage_on_behalf(emp, stage)
    old = emp.status
    new_status = pipeline.next_status_after(stage)
    advance_employee_to_stage(emp, new_status)
    notify(emp, f"{pipeline.STAGE_LABELS[stage]} completed on your behalf",
           "An administrator completed this step for you and advanced your onboarding.",
           link="/employee/home/", category="info")
    log_activity(request, action="bypass_stage", entity_type="employee", entity_id=emp.id,
                 description=f"Bypassed {stage} on behalf ({old} -> {emp.status}) for {emp.email}")
    messages.success(request, f"{pipeline.STAGE_LABELS[stage]} bypassed — employee advanced.")
    return redirect("admin_employee_detail", user_id=emp.id)


@permission_required("bypass_stages")
@require_http_methods(["POST"])
def bypass_all_stages(request, user_id):
    emp = _get_employee(user_id)
    remaining = pipeline.remaining_stages(emp)
    if not remaining:
        messages.info(request, "This employee has already completed onboarding.")
        return redirect("admin_employee_detail", user_id=emp.id)
    old = emp.status
    for stage in remaining:
        _complete_stage_on_behalf(emp, stage)
    advance_employee_to_stage(emp, "completed")
    notify(emp, "Onboarding completed on your behalf",
           "An administrator completed all remaining steps for you.",
           link="/employee/home/", category="success")
    log_activity(request, action="bypass_all_stages", entity_type="employee", entity_id=emp.id,
                 description=f"Bypassed all remaining stages ({old} -> completed) for {emp.email}: "
                             + ", ".join(remaining))
    messages.success(request, "All remaining stages bypassed — employee marked completed.")
    return redirect("admin_employee_detail", user_id=emp.id)


CMS_KINDS = [
    ("portal_slider", "Sliders"),
    ("management_message", "Management Messages"),
    ("event", "Upcoming Events"),
    ("news", "Latest News"),
    ("portal_gallery", "Gallery"),
    ("portal_video", "Videos"),
]


@permission_required("manage_landing_page")
@require_http_methods(["GET", "POST"])
def portal_cms(request):
    """Manage the landing-page content: sliders, management messages, gallery, videos."""
    valid = {k for k, _ in CMS_KINDS}
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            Content.objects.filter(id=request.POST.get("item_id"),
                                   kind__in=valid).delete()
            messages.success(request, "Item removed.")
        elif action == "toggle":
            c = Content.objects.filter(id=request.POST.get("item_id"), kind__in=valid).first()
            if c:
                c.is_active = not c.is_active
                c.save(update_fields=["is_active"])
        else:  # add
            kind = request.POST.get("kind")
            if kind not in valid:
                messages.error(request, "Unknown content type.")
                return redirect("admin_portal_cms")
            meta = {}
            if request.POST.get("video_url"):
                meta["video_url"] = request.POST.get("video_url").strip()
            if request.POST.get("link"):
                meta["link"] = request.POST.get("link").strip()
            if request.POST.get("author"):
                meta["author"] = request.POST.get("author").strip()
            if request.POST.get("role_title"):
                meta["role_title"] = request.POST.get("role_title").strip()
            event_date = (request.POST.get("event_date") or "").strip()
            if event_date:
                from datetime import datetime
                try:
                    d = datetime.strptime(event_date, "%Y-%m-%d")
                    meta["date"] = event_date
                    meta["month"] = d.strftime("%b").upper()
                    meta["day"] = d.strftime("%d")
                except ValueError:
                    pass
            try:
                order = int(request.POST.get("display_order") or 0)
            except ValueError:
                order = 0
            c = Content(
                kind=kind, tenant=request.user.tenant,
                title=(request.POST.get("title") or "").strip(),
                body=(request.POST.get("body") or "").strip(),
                meta=meta, display_order=order, is_active=True,
                created_by=request.user,
            )
            if request.FILES.get("file"):
                c.file = request.FILES["file"]
            c.save()
            messages.success(request, "Added to the landing page.")
        return redirect("admin_portal_cms")

    grouped = {k: list(Content.objects.filter(kind=k).order_by("display_order", "-created_at"))
               for k, _ in CMS_KINDS}
    return render(request, "admin/portal_cms.html", {"kinds": CMS_KINDS, "grouped": grouped})


@permission_required("manage_organization")
@require_http_methods(["GET", "POST"])
def organization(request):
    """Manage organizational structure options."""
    valid_kinds = {k for k, _ in ORG_KINDS}
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            kind = request.POST.get("kind")
            name = (request.POST.get("name") or "").strip()
            if kind not in valid_kinds or not name:
                messages.error(request, "Choose a type and enter a name.")
            elif OrgUnit.objects.filter(kind=kind, name__iexact=name).exists():
                messages.warning(request, f'"{name}" already exists.')
            else:
                OrgUnit.objects.create(
                    kind=kind, name=name,
                    description=(request.POST.get("description") or "").strip(),
                    tenant=request.user.tenant, is_active=True,
                )
                messages.success(request, f'Added "{name}".')
        elif action == "update":
            ou = OrgUnit.objects.filter(id=request.POST.get("option_id")).first()
            if ou:
                ou.name = (request.POST.get("name") or "").strip()
                ou.description = (request.POST.get("description") or "").strip()
                ou.save()
                messages.success(request, f'Updated "{ou.name}".')
        elif action == "delete":
            ou = OrgUnit.objects.filter(id=request.POST.get("option_id")).first()
            if ou:
                if ou.kind == "department" and ou.members.exists():
                    messages.error(request, f'Cannot delete "{ou.name}" - employees are assigned to it.')
                else:
                    ou.delete()
                    messages.success(request, "Option deleted.")
        return redirect("admin_organization")

    return render(request, "admin/organization.html", {
        "kinds": ORG_KINDS,
        "options": _org_options(),
    })


SMTP_KEYS = ["smtp_host", "smtp_port", "smtp_user", "smtp_from_name", "smtp_from_email"]
SMTP_FLAGS = ["smtp_use_tls", "smtp_use_ssl"]


@roles_required("super_admin")
@require_http_methods(["GET", "POST"])
def email_settings(request):
    from ..email_service import send_email, smtp_configured
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "test":
            ok, err = send_email(request.user.email, "OnboardHub test email",
                                 "This is a test email from your OnboardHub SMTP settings. "
                                 "If you received it, email is working.")
            if ok:
                messages.success(request, f"Test email sent to {request.user.email}.")
            else:
                messages.error(request, f"Test failed: {err}")
            return redirect("admin_email_settings")
        for key in SMTP_KEYS:
            AppSetting.set(key, (request.POST.get(key) or "").strip(), user=request.user)
        # Password: only overwrite when a new value is provided.
        new_pw = request.POST.get("smtp_password")
        if new_pw:
            AppSetting.set("smtp_password", new_pw, user=request.user)
        for flag in SMTP_FLAGS:
            AppSetting.set(flag, "true" if request.POST.get(flag) else "false", user=request.user)
        log_activity(request, action="update_smtp_settings", entity_type="settings",
                     description="Updated SMTP settings")
        messages.success(request, "Email settings saved.")
        return redirect("admin_email_settings")

    smtp = {k: AppSetting.get(k, "") or "" for k in SMTP_KEYS}
    smtp["smtp_use_tls"] = (AppSetting.get("smtp_use_tls", "true") or "true").lower() == "true"
    smtp["smtp_use_ssl"] = (AppSetting.get("smtp_use_ssl", "false") or "false").lower() == "true"
    smtp["has_password"] = bool(AppSetting.get("smtp_password"))
    return render(request, "admin/email_settings.html", {
        "smtp": smtp, "configured": smtp_configured(),
    })


BRANDING_DEFAULTS = {
    "site_title": "OnboardHub",
    "primary_color": "#1d2b4f", "accent_color": "#324b8a",
    "sidebar_bg": "#1d2b4f", "sidebar_hover": "#2a3a66", "sidebar_active": "#324b8a",
    "nav_text_color": "#ffffff", "nav_active_text_color": "#ffffff",
    "page_bg_color": "#f8fafc",
    "font_family": "Inter", "radius_scale": "rounded",
    "density": "comfortable", "button_style": "rounded", "card_style": "glass",
}
BRANDING_COLOR_KEYS = ["primary_color", "accent_color", "sidebar_bg", "sidebar_hover",
                       "sidebar_active", "nav_text_color", "nav_active_text_color", "page_bg_color"]
BRANDING_SELECT_KEYS = ["font_family", "radius_scale", "density", "button_style", "card_style"]


@permission_required("manage_appearance")
@require_http_methods(["GET", "POST"])
def branding(request):
    import os
    from django.conf import settings as dj_settings
    if request.method == "POST":
        if request.POST.get("action") == "reset":
            AppSetting.objects.filter(
                key__in=list(BRANDING_DEFAULTS) + ["site_logo"]
            ).delete()
            messages.success(request, "Branding reset to defaults.")
            return redirect("admin_branding")
        AppSetting.set("site_title", (request.POST.get("site_title") or "").strip(), user=request.user)
        for k in BRANDING_COLOR_KEYS + BRANDING_SELECT_KEYS:
            AppSetting.set(k, (request.POST.get(k) or "").strip(), user=request.user)
        if request.POST.get("remove_logo"):
            AppSetting.set("site_logo", "", user=request.user)
        logo = request.FILES.get("logo")
        if logo:
            folder = os.path.join(dj_settings.MEDIA_ROOT, "branding")
            os.makedirs(folder, exist_ok=True)
            ext = (logo.name.rsplit(".", 1)[-1].lower() if "." in logo.name else "png")
            fname = f"logo.{ext}"
            with open(os.path.join(folder, fname), "wb") as fh:
                for chunk in logo.chunks():
                    fh.write(chunk)
            AppSetting.set("site_logo", f"media/branding/{fname}", user=request.user)
        log_activity(request, action="update_branding", entity_type="settings",
                     description="Updated branding/appearance")
        messages.success(request, "Branding saved — the whole portal now reflects your changes.")
        return redirect("admin_branding")

    current = {k: (AppSetting.get(k) or BRANDING_DEFAULTS[k]) for k in BRANDING_DEFAULTS}
    return render(request, "admin/branding.html", {
        "b": current,
        "logo": AppSetting.get("site_logo", ""),
        "fonts": ["Inter", "Plus Jakarta Sans", "Roboto", "Poppins"],
        "radius_scales": ["sharp", "rounded", "pill"],
        "densities": ["comfortable", "compact"],
        "button_styles": ["rounded", "pill", "square"],
        "card_styles": ["glass", "flat"],
        "color_fields": [
            ("primary_color", "Primary"), ("accent_color", "Accent"),
            ("sidebar_bg", "Top bar background"), ("sidebar_hover", "Top bar hover"),
            ("sidebar_active", "Active item"), ("nav_text_color", "Nav text"),
            ("nav_active_text_color", "Active nav text"), ("page_bg_color", "Page background"),
        ],
    })


@permission_required("manage_automation_rules")
@require_http_methods(["GET", "POST"])
def automation(request):
    from .. import automation as auto
    import secrets as _secrets
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "run_reminders":
            sent = auto.run_reminders()
            messages.success(request, f"Reminders run — {sent} sent.")
            return redirect("admin_automation")
        key = auto.AUTOMATION_KEY if request.POST.get("kind") == "automation" else auto.REMINDER_KEY
        rules = auto.get_rules(key)
        if action == "delete":
            rid = request.POST.get("rule_id")
            rules = [r for r in rules if r.get("id") != rid]
        elif action == "add":
            if key == auto.AUTOMATION_KEY:
                rules.append({
                    "id": _secrets.token_hex(4),
                    "name": (request.POST.get("name") or "Rule").strip(),
                    "trigger": request.POST.get("trigger"),
                    "action": request.POST.get("rule_action") or "notify_employee",
                    "message": (request.POST.get("message") or "").strip(),
                    "active": True,
                })
            else:
                rules.append({
                    "id": _secrets.token_hex(4),
                    "name": (request.POST.get("name") or "Reminder").strip(),
                    "status": request.POST.get("status"),
                    "days": request.POST.get("days") or "0",
                    "message": (request.POST.get("message") or "").strip(),
                    "active": True,
                })
        auto.save_rules(key, rules, user=request.user)
        log_activity(request, action="update_automation", entity_type="settings",
                     description=f"Updated {key}")
        messages.success(request, "Saved.")
        return redirect("admin_automation")

    return render(request, "admin/automation.html", {
        "automation_rules": auto.get_rules(auto.AUTOMATION_KEY),
        "reminder_rules": auto.get_rules(auto.REMINDER_KEY),
        "actions": auto.ACTIONS,
        "statuses": EMPLOYEE_STATUSES,
    })


@roles_required("super_admin")
@require_http_methods(["GET", "POST"])
@staff_required
def email_templates(request):
    from ..services.email_service import (EMAIL_TEMPLATE_DEFAULTS, EMAIL_TAGS, get_email_templates,
                                          save_email_templates, all_email_templates,
                                          upsert_custom_template, delete_custom_template)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_template":
            created = upsert_custom_template(
                request.POST.get("new_key"), request.POST.get("new_label"),
                request.POST.get("new_subject"), request.POST.get("new_body"),
                user=request.user)
            messages.success(request, "Template added." if created
                             else "Couldn't add template — pick a unique name.")
        elif action == "delete_template":
            delete_custom_template(request.POST.get("template_key"), user=request.user)
            messages.success(request, "Template deleted.")
        else:
            # Save edits: built-in overrides go to "email_templates"; customs are upserted.
            data = get_email_templates()
            for key in EMAIL_TEMPLATE_DEFAULTS:
                data[key] = {
                    "subject": (request.POST.get(f"{key}_subject") or "").strip(),
                    "body": request.POST.get(f"{key}_body") or "",
                }
            save_email_templates(data, user=request.user)
            for t in all_email_templates():
                if t["custom"]:
                    upsert_custom_template(
                        t["key"], t["label"],
                        request.POST.get(f"{t['key']}_subject"),
                        request.POST.get(f"{t['key']}_body"), user=request.user)
            log_activity(request, action="update_email_templates", entity_type="settings",
                         description="Updated email templates")
            messages.success(request, "Email templates saved.")
        return redirect("admin_email_templates")

    return render(request, "admin/email_templates.html", {
        "templates": all_email_templates(),
        "email_tags": [{"tag": k, "desc": v[0], "sample": v[1]} for k, v in EMAIL_TAGS.items()],
    })


@roles_required("super_admin")
@require_http_methods(["GET"])
def email_logs(request):
    """View recent email sending logs."""
    from ..services.email_service import EmailService

    # Get logs with optional filtering
    all_logs = EmailService.get_logs(limit=500)

    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter:
        all_logs = [log for log in all_logs if log.get('status') == status_filter]

    # Filter by template if provided
    template_filter = request.GET.get('template')
    if template_filter:
        all_logs = [log for log in all_logs if log.get('template_key') == template_filter]

    # Reverse to show newest first
    all_logs = list(reversed(all_logs))

    # Paginate
    page = int(request.GET.get('page', 1))
    per_page = 50
    start = (page - 1) * per_page
    logs = all_logs[start:start + per_page]
    total_pages = (len(all_logs) + per_page - 1) // per_page

    return render(request, "admin/email_logs.html", {
        "logs": logs,
        "page": page,
        "total_pages": total_pages,
        "status_filter": status_filter,
        "template_filter": template_filter,
        "statuses": ['sent', 'failed'],
    })


@roles_required("super_admin")
@require_http_methods(["GET"])
def email_statistics(request):
    """Email sending statistics and analytics."""
    from ..services.email_service import EmailService
    from collections import Counter
    from datetime import datetime, timedelta

    all_logs = EmailService.get_logs(limit=1000)

    # Calculate stats
    total = len(all_logs)
    sent = sum(1 for log in all_logs if log.get('status') == 'sent')
    failed = sum(1 for log in all_logs if log.get('status') == 'failed')
    success_rate = (sent / total * 100) if total > 0 else 0

    # Group by template
    template_counts = Counter(log.get('template_key') for log in all_logs)
    template_stats = [
        {
            'template': k,
            'count': v,
            'percentage': (v / total * 100) if total > 0 else 0,
        }
        for k, v in template_counts.most_common()
    ]

    # Last 7 days trend
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    daily_stats = {i: {'sent': 0, 'failed': 0} for i in range(7)}

    for log in all_logs:
        try:
            log_date = datetime.fromisoformat(log.get('sent_at', ''))
            if log_date >= week_ago:
                days_ago = (now.date() - log_date.date()).days
                if 0 <= days_ago < 7:
                    if log.get('status') == 'sent':
                        daily_stats[days_ago]['sent'] += 1
                    else:
                        daily_stats[days_ago]['failed'] += 1
        except:
            pass

    # Top recipients
    recipient_counts = Counter(log.get('to_email') for log in all_logs)
    top_recipients = recipient_counts.most_common(10)

    return render(request, "admin/email_statistics.html", {
        "total_emails": total,
        "sent_count": sent,
        "failed_count": failed,
        "success_rate": round(success_rate, 1),
        "template_stats": template_stats,
        "daily_stats": [daily_stats[i] for i in range(7)],
        "top_recipients": [{'email': k, 'count': v} for k, v in top_recipients],
    })


@roles_required("super_admin")
@require_http_methods(["GET", "POST"])
def roles(request):
    role = request.POST.get("role") or request.GET.get("role") or "admin"
    if role not in editable_roles():
        role = "admin"
    selected_custom_role = next((r for r in custom_roles() if r["key"] == role), None)
    role_choices = [r for r in all_roles(include_super=False)]
    if request.method == "POST":
        action = request.POST.get("action") or "save_permissions"
        perms = request.POST.getlist("permissions")
        if action == "delete_custom_role":
            if delete_custom_role(role, user=request.user):
                log_activity(request, action="delete_role", entity_type="role",
                             description=f"Deleted custom role '{role}'")
                messages.success(request, f"Custom role '{role}' deleted.")
                return redirect("/admin/roles/")
            messages.error(request, "That custom role could not be deleted.")
            return redirect(f"/admin/roles/?role={role}")
        if action == "save_custom_role":
            custom_key = request.POST.get("custom_role_key") or (selected_custom_role["key"] if selected_custom_role else "")
            custom_label = request.POST.get("custom_role_label") or custom_key or role_label(role)
            created = upsert_custom_role(
                custom_key,
                custom_label,
                request.POST.get("custom_role_base"),
                request.POST.get("custom_role_scope_type"),
                perms,
                user=request.user,
            )
            if created:
                log_activity(request, action="save_role", entity_type="role",
                             description=f"Saved custom role '{created['label']}' ({created['key']})")
                messages.success(request, f"Custom role '{created['label']}' saved.")
                return redirect(f"/admin/roles/?role={created['key']}")
            messages.error(request, "Please provide a unique custom role key or select an editable custom role.")
            return redirect(f"/admin/roles/?role={role}")
        set_role_permissions(role, perms, user=request.user)
        log_activity(request, action="edit_role_permissions", entity_type="role",
                     description=f"Updated default permissions for role '{role}'")
        messages.success(request, f"Permissions for '{role}' updated.")
        return redirect(f"/admin/roles/?role={role}")
    return render(request, "admin/roles.html", {
        "permission_categories": PERMISSION_CATEGORIES,
        "selected_perms": resolve_role_permissions(role),
        "role": role,
        "selected_role_label": role_label(role),
        "role_choices": role_choices,
        "selected_custom_role": selected_custom_role,
        "selected_role_meta": {
            "base": role_base(role),
            "scope_type": role_scope_type(role) or "",
        },
        "role_perms_map": role_permission_map(),
    })


@permission_required("manage_users")
@require_http_methods(["POST"])
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if user.id == request.user.id:
        messages.error(request, "You cannot delete your own account.")
        return redirect("admin_users")
    user.status = "deleted"
    user.is_active = False
    user.save(update_fields=["status", "is_active"])
    log_activity(request, action="delete_user", entity_type="user", entity_id=user.id,
                 description=f"Soft-deleted {user.email}")
    messages.success(request, "User removed.")
    return redirect("admin_employees" if user.role == "employee" else "admin_users")


# ── Forms / Form Builder ─────────────────────────────────────────────────────
STAGE_CHOICES = ["pre_onboarding", "onboarding", "post_onboarding", "general"]


@permission_required("manage_forms")
def forms_list(request):
    forms = Form.objects.all().order_by("stage", "display_order", "id")
    return render(request, "admin/forms.html", {"forms": forms})


@permission_required("manage_forms")
@require_http_methods(["GET", "POST"])
def create_form(request):
    if request.method == "POST":
        form = _save_form_from_post(request, Form())
        messages.success(request, "Form created.")
        return redirect("admin_edit_form", form_id=form.id)
    return render(request, "admin/edit_form.html", {
        "form": None, "stages": STAGE_CHOICES, "schema_json": json.dumps({"sections": []}),
    })


@permission_required("manage_forms")
@require_http_methods(["GET", "POST"])
def edit_form(request, form_id):
    form = get_object_or_404(Form, id=form_id)
    if request.method == "POST":
        _save_form_from_post(request, form)
        messages.success(request, "Form saved.")
        return redirect("admin_edit_form", form_id=form.id)
    return render(request, "admin/edit_form.html", {
        "form": form, "stages": STAGE_CHOICES,
        "schema_json": json.dumps(form.schema or {"sections": []}),
    })


def _save_form_from_post(request, form):
    form.name = (request.POST.get("name") or "Untitled Form").strip()
    form.description = (request.POST.get("description") or "").strip()
    form.stage = request.POST.get("stage") or "pre_onboarding"
    form.employee_type = (request.POST.get("employee_type") or "").strip() or None
    form.is_active = bool(request.POST.get("is_active"))
    form.form_kind = request.POST.get("form_kind") or "form"
    try:
        form.display_order = int(request.POST.get("display_order") or 0)
    except ValueError:
        form.display_order = 0
    raw_schema = request.POST.get("schema_json") or '{"sections": []}'
    try:
        schema = json.loads(raw_schema)
        if not isinstance(schema, dict) or "sections" not in schema:
            schema = {"sections": []}
    except json.JSONDecodeError:
        schema = {"sections": []}
    form.schema = schema
    if form.is_anonymous or request.POST.get("generate_share"):
        form.generate_share_token()
    if form.tenant_id is None:
        form.tenant = request.user.tenant
    form.save()
    log_activity(request, action="save_form", entity_type="form", entity_id=form.id,
                 description=f"Saved form {form.name}")
    return form


@permission_required("manage_forms")
@require_http_methods(["POST"])
def delete_form(request, form_id):
    form = get_object_or_404(Form, id=form_id)
    name = form.name
    form.delete()
    messages.success(request, f"Deleted form '{name}'.")
    return redirect("admin_forms")


# ── Onboarding documents ─────────────────────────────────────────────────────
@permission_required("manage_documents")
@require_http_methods(["GET", "POST"])
def onboarding_documents(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            OnboardingDocument.objects.filter(id=request.POST.get("doc_id")).delete()
            messages.success(request, "Document deleted.")
        else:
            doc = OnboardingDocument(
                title=(request.POST.get("title") or "Untitled").strip(),
                description=(request.POST.get("description") or "").strip(),
                stage=request.POST.get("stage") or "onboarding",
                body=(request.POST.get("body") or "").strip(),
                is_required=bool(request.POST.get("is_required")),
                is_active=True,
                tenant=request.user.tenant,
            )
            if request.FILES.get("file"):
                doc.file = request.FILES["file"]
            doc.save()
            messages.success(request, "Document added.")
        return redirect("admin_onboarding_documents")
    docs = OnboardingDocument.objects.all().order_by("stage", "display_order")
    return render(request, "admin/onboarding_documents.html", {
        "docs": docs, "stages": STAGE_CHOICES,
    })


# ── Medical requirements / review ────────────────────────────────────────────
@permission_required("manage_medical_requirements")
@require_http_methods(["GET", "POST"])
def medical_requirements(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_requirement":
            MedicalRecord.objects.create(
                requirement_name=(request.POST.get("requirement_name") or "Requirement").strip(),
                description=(request.POST.get("description") or "").strip(),
                is_required=bool(request.POST.get("is_required")),
                is_catalog=True,
                is_active=True,
                meta=_medical_requirement_meta(request),
                tenant=request.user.tenant,
            )
            messages.success(request, "Medical requirement added.")
        elif action == "edit_requirement":
            rec = get_object_or_404(MedicalRecord, id=request.POST.get("requirement_id"),
                                    is_catalog=True)
            rec.requirement_name = (request.POST.get("requirement_name") or rec.requirement_name).strip()
            rec.description = (request.POST.get("description") or "").strip()
            rec.is_required = bool(request.POST.get("is_required"))
            rec.is_active = bool(request.POST.get("is_active"))
            rec.meta = _medical_requirement_meta(request)
            rec.save(update_fields=[
                "requirement_name", "description", "is_required", "is_active", "meta",
            ])
            messages.success(request, "Medical requirement updated.")
        elif action == "toggle_requirement":
            rec = get_object_or_404(MedicalRecord, id=request.POST.get("requirement_id"),
                                    is_catalog=True)
            rec.is_active = not rec.is_active
            rec.save(update_fields=["is_active"])
            messages.success(request, "Medical requirement updated.")
        elif action == "delete_requirement":
            rec = get_object_or_404(MedicalRecord, id=request.POST.get("requirement_id"),
                                    is_catalog=True)
            name = rec.requirement_name
            rec.delete()
            messages.success(request, f"Deleted medical requirement '{name}'.")
        return redirect("admin_medical_requirements")

    catalog = MedicalRecord.objects.filter(is_catalog=True).order_by("requirement_name")
    return render(request, "admin/medical_requirements.html", {
        "catalog": catalog,
    })


def _medical_requirement_meta(request):
    meta = {}
    gender = (request.POST.get("gender") or "").strip().lower()
    if gender in ("male", "female"):
        meta["gender"] = gender
    min_age = (request.POST.get("min_age") or "").strip()
    if min_age.isdigit():
        meta["min_age"] = int(min_age)
    return meta
