"""Admin console: dashboard, employees, users, form builder, documents, medical."""
import csv
import io
import json
import os
import secrets
import shutil

from typing import Dict, List, Optional

from django.apps import apps
from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib import messages
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_http_methods
from openpyxl import Workbook, load_workbook

from .. import pipeline
from ..decorators import staff_required, permission_required, roles_required
from ..medical_match import medical_applicability
from ..models import (
    User, OrgUnit, AppSetting, Form, FormResponse, OnboardingDocument, MedicalRecord,
    ReviewMessage, Content, Engagement, Notification, AuditLog, StageDefinition,
    StageTemplate, EmployeeStagePath, OfferWorkflow, STATUS_CHOICES,
)
from ..models_offers import OfferTemplate, OfferEmailTemplate, OfferFieldDefinition, Offer, OfferFieldValue

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


def _attach_current_stage_info(users):
    """Annotate users with the live stage label/state used across admin/HRBP views."""
    for user in users:
        stage_key = pipeline.current_stage(user)
        if stage_key:
            user.current_stage_key = stage_key
            user.current_stage_label = pipeline.STAGE_LABELS.get(
                stage_key,
                stage_key.replace("_", " ").title(),
            )
            user.current_stage_state = pipeline.stage_state(user, stage_key)
        elif user.status == "completed":
            user.current_stage_key = None
            user.current_stage_label = "Completed"
            user.current_stage_state = "completed"
        else:
            user.current_stage_key = None
            user.current_stage_label = "Not started"
            user.current_stage_state = "pending"
    return users


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
        qs = qs.filter(department_id__in=depts) if depts else qs.none()
    elif scope_type == "location":
        locs = (viewer.scope or {}).get("locations") or []
        qs = qs.filter(location_code__in=locs) if locs else qs.none()

    if viewer.role == "medical_approver":
        from ..models import OfferWorkflow
        from ..models_offers import Offer
        accepted_emp_ids = list(OfferWorkflow.objects.filter(status="accepted").values_list("employee_id", flat=True))
        accepted_emp_ids += list(Offer.objects.filter(status="accepted").values_list("candidate_user_id", flat=True))
        qs = qs.filter(id__in=accepted_emp_ids)

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
        example = ["Test Employee", "testemployee1@company.com", "EMP-1001", "Engineering",
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
            existing = User.objects.filter(email__iexact=email).first()
            if existing and existing.status != "deleted":
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
                if existing and existing.status == "deleted":
                    # Reactivate the soft-deleted user
                    existing.status = "pending"
                    existing.is_active = True
                    existing.full_name = name
                    existing.must_change_password = True
                    existing.employee_id = row.get("employee_id") or existing.employee_id
                    existing.position_title = row.get("designation") or None
                    existing.grade = row.get("grade") or None
                    existing.location_code = row.get("location") or None
                    existing.payroll = row.get("payroll") or None
                    existing.employee_type = row.get("employee_type") or None
                    existing.gender = (row.get("gender") or "").lower() or None
                    existing.department = dept
                    existing.date_of_birth = _parse_date(row.get("date_of_birth"))
                    existing.date_of_joining = _parse_date(row.get("date_of_joining"))
                    existing.set_password(temp)
                    existing.save()
                else:
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


@permission_required("export_data")
@require_http_methods(["POST"])
def export_employee_package(request, user_id):
    """Export selected onboarding stages as a structured ZIP archive."""
    import zipfile
    from datetime import datetime

    emp = _get_employee(user_id)
    if not can_view_employee(request.user, emp):
        messages.error(request, "This employee is outside your scope.")
        return redirect("admin_employees")

    available_stages = {"medical", "pre_onboarding", "onboarding", "post_onboarding"}
    selected = set(request.POST.getlist("sections")) & available_stages
    if not selected:
        messages.error(request, "Select at least one section to export.")
        return redirect("admin_employee_detail", user_id=emp.id)

    def safe_name(value, fallback="file"):
        return get_valid_filename(str(value or fallback)) or fallback

    def xlsx_bytes(headers, rows):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Export"
        sheet.append(headers)
        for row in rows:
            sheet.append(["" if value is None else str(value) for value in row])
        for cell in sheet[1]:
            cell.font = cell.font.copy(bold=True)
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(
                48, max(14, max(len(str(cell.value or "")) for cell in column) + 2)
            )
        output = io.BytesIO()
        workbook.save(output)
        return output.getvalue()

    def add_storage_file(archive, storage_name, archive_name):
        if not storage_name:
            return
        try:
            with default_storage.open(storage_name, "rb") as source:
                archive.writestr(archive_name, source.read())
        except (OSError, ValueError):
            # Missing legacy uploads should not prevent the remaining package.
            return

    def add_form_response(archive, response, stage_folder):
        form = response.form
        fields = form.get_all_fields()
        field_names = [field["field_name"] for field in fields]
        labels = [field.get("label") or field["field_name"] for field in fields]
        values = []
        for name in field_names:
            value = (response.answers or {}).get(name, "")
            values.append(", ".join(map(str, value)) if isinstance(value, list) else value)
        form_name = safe_name(form.name, f"form_{form.id}")
        archive.writestr(
            f"{stage_folder}/Forms/{form_name}.xlsx",
            xlsx_bytes(["Submitted", "Status"] + labels, [[
                timezone.localtime(response.submitted_at).strftime("%Y-%m-%d %H:%M"),
                "Draft" if response.is_draft else "Submitted",
            ] + values]),
        )
        for field_name, storage_name in (response.files or {}).items():
            names = storage_name if isinstance(storage_name, list) else [storage_name]
            for index, name in enumerate(names, start=1):
                if name:
                    filename = safe_name(os.path.basename(str(name)), "upload")
                    prefix = safe_name(field_name, "upload")
                    suffix = f"_{index}" if len(names) > 1 else ""
                    add_storage_file(archive, name, f"{stage_folder}/Files/{form_name}/{prefix}{suffix}_{filename}")

    zip_buffer = io.BytesIO()
    stage_labels = {
        "medical": "Medical",
        "pre_onboarding": "Pre-Onboarding",
        "onboarding": "Onboarding",
        "post_onboarding": "Post-Onboarding",
    }
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", "Selected employee onboarding export. Each stage contains its spreadsheets and uploaded files.\n")
        if "medical" in selected:
            records = MedicalRecord.objects.filter(employee=emp, is_catalog=False)
            medical_rows = []
            for record in records:
                medical_rows.append([
                    record.requirement_name, record.get_status_display(), record.review_notes or "",
                    timezone.localtime(record.reviewed_at).strftime("%Y-%m-%d %H:%M") if record.reviewed_at else "",
                ])
                if record.file:
                    filename = safe_name(os.path.basename(record.file.name), "medical_file")
                    add_storage_file(archive, record.file.name, f"Medical/Files/{safe_name(record.requirement_name, 'test')}_{filename}")
            archive.writestr("Medical/medical_records.xlsx", xlsx_bytes(
                ["Test / Requirement", "Status", "Review notes", "Reviewed at"], medical_rows
            ))

        for stage in selected - {"medical"}:
            folder = stage_labels[stage]
            responses = FormResponse.objects.filter(employee=emp, form__stage=stage).select_related("form")
            for response in responses:
                add_form_response(archive, response, folder)
            for document in OnboardingDocument.objects.filter(stage=stage, is_active=True):
                if not document.signed_by(emp.id):
                    continue
                document_name = safe_name(document.title, f"document_{document.id}")
                if document.file:
                    filename = safe_name(os.path.basename(document.file.name), "document")
                    add_storage_file(archive, document.file.name, f"{folder}/Documents/{document_name}_{filename}")
                elif document.body:
                    archive.writestr(f"{folder}/Documents/{document_name}.html", document.body)

    log_activity(request, action="export_employee_package", entity_type="employee", entity_id=emp.id,
                 description=f"Exported: {', '.join(sorted(selected))}")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_name(emp.full_name, 'employee')}_onboarding_{timestamp}.zip"
    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@permission_required("manage_users")
@require_http_methods(["POST"])
def reset_user_password(request, user_id):
    """Issue a one-time temporary password from an explicit admin action."""
    user = get_object_or_404(User, id=user_id)
    if user.status == "deleted":
        messages.error(request, "A deleted user cannot be issued a new password.")
    else:
        temp_password = secrets.token_urlsafe(9)
        user.set_password(temp_password)
        user.must_change_password = True
        user.save(update_fields=["password", "must_change_password", "updated_at"])
        notify(
            user,
            "Your password was reset",
            f"An administrator reset your password. Your temporary password is: {temp_password}. "
            "You must choose a new password when you next sign in.",
            link="/change-password/", category="warning",
        )
        from ..services.email_service import EmailService, _big_login_cta
        EmailService.send_email(
            to_email=user.email,
            template_key="credentials_reset",
            context={
                "full_name": user.full_name or user.email,
                "email": user.email,
                "temp_password": temp_password,
                "big_login_cta": _big_login_cta(request.build_absolute_uri("/login/")),
            },
            user=user,
        )
        log_activity(
            request, action="admin_password_reset", entity_type="user", entity_id=user.id,
            description=f"Administrator reset the password for {user.email}",
        )
        messages.success(request, f"Temporary password for {user.full_name}: {temp_password}")
    next_url = request.POST.get("next") or request.GET.get("next")
    # Validate next_url to prevent open redirect (must be a relative path)
    if next_url and (next_url.startswith('http') or not next_url.startswith('/')):
        next_url = None
    if not next_url:
        if user.role == "employee":
            next_url = reverse("admin_employee_detail", args=[user.id])
        else:
            next_url = reverse("admin_users")
    return redirect(next_url)


@permission_required("send_offer")
def offers(request):
    from ..models_offers import OfferTemplate, OfferEmailTemplate, OfferFieldDefinition, Offer
    offer_templates = OfferTemplate.objects.filter(tenant=request.user.tenant) if request.user.tenant else OfferTemplate.objects.all()
    email_templates = OfferEmailTemplate.objects.filter(tenant=request.user.tenant) if request.user.tenant else OfferEmailTemplate.objects.all()
    offer_fields = OfferFieldDefinition.objects.filter(tenant=request.user.tenant) if request.user.tenant else OfferFieldDefinition.objects.all()
    offers_qs = Offer.objects.filter(tenant=request.user.tenant) if request.user.tenant else Offer.objects.all()

    scoped_users = scoped_employee_qs(request.user, User.objects.filter(role__in=_employee_role_keys()).exclude(status="deleted"))
    scoped_user_ids = scoped_users.values_list("id", flat=True)
    offers_qs = offers_qs.filter(candidate_user_id__in=scoped_user_ids)

    return render(request, "admin/offers.html", {
        "offers": offers_qs.select_related("candidate_user", "created_by").order_by("-created_at"),
        "employees": scoped_users.order_by("full_name"),
        "offer_templates": offer_templates,
        "email_templates": email_templates,
        "offer_fields": offer_fields,
    })


@permission_required("view_offer_analytics")
def offers_analytics_page(request):
    """Render an admin-facing analytics page that fetches JSON from the analytics API."""
    return render(request, "admin/offers_analytics.html", {})


@permission_required("manage_templates")
@require_http_methods(["GET", "POST"])
def offer_templates_manage(request):
    """List, create, and update OfferTemplates from the admin UI."""
    from ..models_offers import OfferTemplate
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        description = (request.POST.get("description") or "").strip()
        html_content = request.POST.get("html_content") or ""
        template_id = request.POST.get("template_id")
        if not name:
            messages.error(request, "Template name is required.")
            return redirect("admin_offer_templates")

        if template_id:
            tpl = get_object_or_404(OfferTemplate, id=template_id)
            tpl.name = name
            tpl.description = description
            tpl.html_content = html_content
            tpl.save()
            messages.success(request, f"Offer template '{name}' updated successfully.")
        else:
            OfferTemplate.objects.create(
                tenant=request.user.tenant,
                name=name,
                description=description,
                html_content=html_content,
                created_by=request.user
            )
            messages.success(request, f"Offer template '{name}' created successfully.")
        return redirect("admin_offer_templates")

    templates = OfferTemplate.objects.filter(tenant=request.user.tenant) if request.user.tenant else OfferTemplate.objects.all()
    return render(request, "admin/offer_templates.html", {"templates": templates.order_by("name")})


@permission_required("manage_templates")
def offer_template_delete(request, template_id):
    """Delete an OfferTemplate."""
    from ..models_offers import OfferTemplate
    tpl = get_object_or_404(OfferTemplate, id=template_id)
    name = tpl.name
    tpl.delete()
    messages.success(request, f"Offer template '{name}' deleted.")
    return redirect("admin_offer_templates")


@permission_required("manage_email_templates")
@require_http_methods(["GET", "POST"])
def offer_email_templates_manage(request):
    """List, create, and update OfferEmailTemplates from admin UI."""
    from ..models_offers import OfferEmailTemplate
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        subject = request.POST.get("subject_template") or ""
        body = request.POST.get("html_body_template") or ""
        email_template_id = request.POST.get("email_template_id")
        if not name:
            messages.error(request, "Email template name is required.")
            return redirect("admin_offer_email_templates")

        if email_template_id:
            tpl = get_object_or_404(OfferEmailTemplate, id=email_template_id)
            tpl.name = name
            tpl.subject_template = subject
            tpl.html_body_template = body
            tpl.save()
            messages.success(request, f"Email template '{name}' updated successfully.")
        else:
            OfferEmailTemplate.objects.create(
                tenant=request.user.tenant,
                name=name,
                subject_template=subject,
                html_body_template=body,
                created_by=request.user
            )
            messages.success(request, f"Email template '{name}' created successfully.")
        return redirect("admin_offer_email_templates")

    templates = OfferEmailTemplate.objects.filter(tenant=request.user.tenant) if request.user.tenant else OfferEmailTemplate.objects.all()
    return render(request, "admin/offer_email_templates.html", {"templates": templates.order_by("name")})


@permission_required("manage_email_templates")
def offer_email_template_delete(request, template_id):
    """Delete an OfferEmailTemplate."""
    from ..models_offers import OfferEmailTemplate
    tpl = get_object_or_404(OfferEmailTemplate, id=template_id)
    name = tpl.name
    tpl.delete()
    messages.success(request, f"Email template '{name}' deleted.")
    return redirect("admin_offer_email_templates")


@permission_required("send_offer")
@require_http_methods(["POST"])
def send_offer(request):
    employee_id = request.POST.get("employee_id")
    if not employee_id:
        messages.error(request, "Please select an employee to send the offer to.")
        return redirect("admin_offers")
    employee = get_object_or_404(User, id=employee_id)

    position_title = (request.POST.get("position_title") or employee.position_title or "Position").strip()
    salary = (request.POST.get("salary") or "").strip()
    currency = (request.POST.get("currency") or "PKR").strip().upper()
    start_date = (request.POST.get("start_date") or "").strip()
    expiry_raw = (request.POST.get("expiry_date") or "").strip()
    try:
        expiry_date = timezone.make_aware(timezone.datetime.fromisoformat(expiry_raw))
    except ValueError:
        messages.error(request, "Enter a valid offer expiry date and time.")
        return redirect("admin_offers")
    if not salary or not start_date:
        messages.error(request, "Salary and proposed start date are required.")
        return redirect("admin_offers")

    email_template_id = request.POST.get("email_template_id")
    offer_template_id = request.POST.get("offer_template_id")
    email_template = None
    if email_template_id:
       email_template = OfferEmailTemplate.objects.filter(id=email_template_id).first()
    template = None
    if offer_template_id:
       template = OfferTemplate.objects.filter(id=offer_template_id).first()
    if template is None and request.user.tenant:
       template = OfferTemplate.objects.filter(tenant=request.user.tenant, is_default=True).first()
    if template is None:
       template = OfferTemplate.objects.filter(is_default=True).first()

    offer_number = f"OFF-{timezone.now():%Y%m%d}-{secrets.token_hex(3).upper()}"
    offer_info = {
       "offer_number": offer_number,
       "position_title": position_title,
       "salary": salary,
       "currency": currency,
       "employment_type": (request.POST.get("employment_type") or "").strip(),
       "start_date": start_date,
       "benefits": (request.POST.get("benefits") or "").strip(),
       "note": (request.POST.get("note") or "").strip(),
       "expiry_date": expiry_date.isoformat(),
    }
    if email_template_id:
       offer_info["email_template_id"] = email_template_id
    if offer_template_id:
       offer_info["offer_template_id"] = offer_template_id

    offer = Offer.objects.create(
       tenant=request.user.tenant,
       template=template,
       email_template=email_template,
       created_by=request.user,
       candidate_name=employee.full_name or employee.email,
       candidate_email=employee.email,
       candidate_user=employee,
       status="draft",
       metadata=offer_info,
    )

    for key, value in {
       "position_title": position_title,
       "salary": salary,
       "currency": currency,
       "start_date": start_date,
       "employment_type": (request.POST.get("employment_type") or "").strip(),
       "benefits": (request.POST.get("benefits") or "").strip(),
       "note": (request.POST.get("note") or "").strip(),
       "expiry_date": expiry_date.isoformat(),
    }.items():
       if value is not None and value != "":
           OfferFieldValue.objects.create(
               offer=offer,
               field_definition=OfferFieldDefinition.objects.filter(tenant=request.user.tenant, key=key).first(),
               value=str(value),
           )

    from ..views.offer_api_views import _perform_offer_send
    tokens = _perform_offer_send(offer, acting_user=request.user, request=request)
    salary_display = f"{currency} {salary}"
    notify(employee, "Your offer is ready", f"Offer {offer_number} for {position_title}: {salary_display}. Review it before {expiry_date:%d %b %Y}.", link="/employee/offers/", category="info")
    log_activity(request, action="send_offer", entity_type="offer", entity_id=offer.id, description=f"Sent {offer_number} to {employee.email}")
    messages.success(request, f"Offer {offer_number} was sent to {employee.full_name}.")
    return redirect("admin_offers")


@permission_required("send_offer")
@require_http_methods(["POST"])
def resend_offer(request, offer_id):
    """Resend a previously rejected offer with updated values/terms."""
    from ..models_offers import Offer, OfferFieldValue, OfferFieldDefinition, OfferEmailTemplate, OfferTemplate
    
    offer = get_object_or_404(Offer, id=offer_id)
    if offer.status != 'rejected':
        messages.error(request, "Only rejected offers can be edited and resent.")
        return redirect("admin_offers")

    position_title = (request.POST.get("position_title") or "").strip()
    salary = (request.POST.get("salary") or "").strip()
    currency = (request.POST.get("currency") or "PKR").strip().upper()
    start_date = (request.POST.get("start_date") or "").strip()
    expiry_raw = (request.POST.get("expiry_date") or "").strip()
    
    try:
        expiry_date = timezone.make_aware(timezone.datetime.fromisoformat(expiry_raw))
    except ValueError:
        messages.error(request, "Enter a valid offer expiry date and time.")
        return redirect("admin_offers")
        
    if not salary or not start_date:
        messages.error(request, "Salary and proposed start date are required.")
        return redirect("admin_offers")

    email_template_id = request.POST.get("email_template_id")
    offer_template_id = request.POST.get("offer_template_id")
    
    email_template = None
    if email_template_id:
        email_template = OfferEmailTemplate.objects.filter(id=email_template_id).first()
    template = None
    if offer_template_id:
        template = OfferTemplate.objects.filter(id=offer_template_id).first()
    if template is None and request.user.tenant:
        template = OfferTemplate.objects.filter(tenant=request.user.tenant, is_default=True).first()
    if template is None:
        template = OfferTemplate.objects.filter(is_default=True).first()

    # Reset statuses to trigger proper re-send and timeline updates
    offer.status = "draft"
    offer.template = template
    offer.email_template = email_template
    offer.rejected_at = None
    offer.accepted_at = None
    offer.sent_at = None
    
    offer_info = dict(offer.metadata or {})
    offer_info.update({
        "position_title": position_title,
        "salary": salary,
        "currency": currency,
        "employment_type": (request.POST.get("employment_type") or "").strip(),
        "start_date": start_date,
        "benefits": (request.POST.get("benefits") or "").strip(),
        "note": (request.POST.get("note") or "").strip(),
        "expiry_date": expiry_date.isoformat(),
    })
    if email_template_id:
        offer_info["email_template_id"] = email_template_id
    elif "email_template_id" in offer_info:
        del offer_info["email_template_id"]
        
    if offer_template_id:
        offer_info["offer_template_id"] = offer_template_id
    elif "offer_template_id" in offer_info:
        del offer_info["offer_template_id"]

    offer.metadata = offer_info
    offer.save()

    # Recreate OfferFieldValues
    OfferFieldValue.objects.filter(offer=offer).delete()
    for key, value in {
        "position_title": position_title,
        "salary": salary,
        "currency": currency,
        "start_date": start_date,
        "employment_type": offer_info["employment_type"],
        "benefits": offer_info["benefits"],
        "note": offer_info["note"],
        "expiry_date": expiry_date.isoformat(),
    }.items():
        if value is not None and value != "":
            OfferFieldValue.objects.create(
                offer=offer,
                field_definition=OfferFieldDefinition.objects.filter(tenant=request.user.tenant, key=key).first(),
                value=str(value),
            )

    # Re-fetch offer to avoid cached relation/prefetched caches
    offer = Offer.objects.get(id=offer.id)
    
    from ..views.offer_api_views import _perform_offer_send
    tokens = _perform_offer_send(offer, acting_user=request.user, request=request)
    
    employee = offer.candidate_user
    if employee:
        employee.status = "offer"
        employee.save(update_fields=["status"])
        
        salary_display = f"{currency} {salary}"
        notify(employee, "Your offer has been updated", 
               f"Offer {offer.offer_number} for {position_title} has been updated. Review it before {expiry_date:%d %b %Y}.", 
               link="/employee/offers/", category="info")

    log_activity(request, action="resend_offer", entity_type="offer", entity_id=offer.id, 
                 description=f"Resent updated offer {offer.offer_number} to {offer.candidate_email}")
                 
    messages.success(request, f"Offer {offer.offer_number} was successfully updated and resent to {offer.candidate_name}.")
    return redirect("admin_offers")


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
    visible_employees = _attach_current_stage_info(list(employees))
    joining_soon = sum(
        1 for emp in visible_employees
        if emp.date_of_joining and today <= emp.date_of_joining <= in_10_days
    )

    # Dashboard sections follow the effective permission set, not a fixed role
    # name, so custom roles and per-user overrides remain in sync.
    is_super_admin = request.user.role == "super_admin"
    is_admin = request.user.role == "admin"
    is_medical_approver = request.user.role == "medical_approver"
    is_hrbp = request.user.role == "hrbp"

    # Count overdue employees (current stage due date passed)
    now = timezone.now()
    overdue_employees = sum(
        1 for emp in visible_employees
        if emp.status != "completed" and emp.stage_due_date and emp.stage_due_date < now
    )

    stats = {
        "total": len(visible_employees),
        "pending": sum(1 for emp in visible_employees if emp.status == "pending"),
        "in_progress": sum(1 for emp in visible_employees if emp.status not in ["completed", "pending", "deleted"]),
        "completed": sum(1 for emp in visible_employees if emp.status == "completed"),
        "on_hold": sum(1 for emp in visible_employees if emp.status == "on_hold"),
        "awaiting_review": sum(1 for emp in visible_employees if emp.status in AWAITING_REVIEW),
        "joining_soon": joining_soon,
        "overdue": overdue_employees,
    }
    recent = sorted(visible_employees, key=lambda e: e.created_at or timezone.now(), reverse=True)[:8]
    review_queue = sorted(
        [e for e in visible_employees if e.status in AWAITING_REVIEW],
        key=lambda e: e.updated_at or e.created_at or timezone.now(),
        reverse=True,
    )[:8]

    path_enrollments = Engagement.objects.filter(kind="enrollment", content__kind="learning_path")
    learning_stats = {
        "paths": Content.objects.filter(kind="learning_path", is_active=True).count(),
        "active": path_enrollments.exclude(status="completed").count(),
        "completed": path_enrollments.filter(status="completed").count(),
        "overdue": path_enrollments.exclude(status="completed").filter(
            due_date__lt=timezone.now().date()).count(),
    }
    medical_review_queue = [e for e in review_queue
                            if pipeline.stage_of_status(e.status) == "medical"]
    can_medical_review = request.user.has_perm_key("medical_review") or request.user.has_perm_key("approve_medical")

    # Dashboard visibility control
    show_medical_tiles = is_super_admin or can_medical_review
    show_people_tiles = request.user.has_perm_key("view_employees")
    show_learning_tiles = (request.user.has_perm_key("view_training")
                           or request.user.has_perm_key("view_programs"))

    # Medical approvers only see medical content; no other tiles
    if is_medical_approver:
        show_people_tiles = False
        show_learning_tiles = False
        recent = sorted(visible_employees, key=lambda e: e.updated_at or e.created_at or timezone.now(), reverse=True)[:8]

    # HRBP sees joining_soon tile if > 0, but table shows stage tracking
    dashboard_review_queue = medical_review_queue if can_medical_review else review_queue
    dashboard_review_title = "Medical Submissions Awaiting Review" if can_medical_review else "Awaiting Your Review"
    dashboard_review_queue = _attach_current_stage_info(list(dashboard_review_queue)) if dashboard_review_queue else []

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
    sort = (request.GET.get("sort") or "date_of_joining").strip()
    direction = (request.GET.get("dir") or "desc").strip().lower()
    visible_cols = request.GET.getlist("cols") or ["name", "email", "department", "stage", "date_of_joining"]

    sort_map = {
        "name": "full_name",
        "email": "email",
        "department": "department__name",
        "stage": "status",
        "date_of_joining": "date_of_joining",
    }

    qs = scoped_employee_qs(request.user, User.objects.filter(role__in=_employee_role_keys())).exclude(status="deleted").select_related("department")
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(email__icontains=q)
                       | Q(employee_id__icontains=q))
    if status:
        qs = qs.filter(status=status)

    order_field = sort_map.get(sort, "date_of_joining")
    if direction == "asc":
        qs = qs.order_by(order_field)
    else:
        qs = qs.order_by(f"-{order_field}")

    employees = _attach_current_stage_info(list(qs))

    return render(request, "admin/employees.html", {
        "employees": employees,
        "q": q,
        "status": status,
        "statuses": EMPLOYEE_STATUSES,
        "sort": sort,
        "dir": direction,
        "visible_columns": visible_cols,
        "column_options": [
            ("name", "Name"),
            ("email", "Email"),
            ("department", "Department"),
            ("stage", "Stage"),
            ("date_of_joining", "Date of Joining"),
        ],
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
    if request.method == "POST" and request.POST.get("action") == "update_workflow" and not request.user.has_perm_key("customize_employee_workflow"):
        messages.error(request, "You do not have permission to customize employee workflows.")
        return redirect("admin_employee_detail", user_id=emp.id)

    if request.method == "POST" and request.POST.get("action") == "update_workflow":
        from ..pipeline_v2 import create_employee_stage_path
        from ..models import StageDefinition

        new_stages = request.POST.getlist("workflow_stages")
        change_reason = request.POST.get("workflow_change_reason", "Manual update from employee profile")

        if new_stages:
            # Validate: only enabled stages can be assigned
            enabled_stages = set(StageDefinition.objects.filter(is_enabled=True).values_list("stage_key", flat=True))
            invalid_stages = set(new_stages) - enabled_stages

            if invalid_stages:
                messages.error(request, f"Invalid stages (disabled or non-existent): {', '.join(invalid_stages)}")
            else:
                create_employee_stage_path(emp, new_stages, change_reason=change_reason, modified_by=request.user)
                log_activity(request, action="update_employee_workflow", entity_type="employee", entity_id=emp.id,
                            description=f"Updated workflow to {', '.join(new_stages)}")
                messages.success(request, "Workflow updated successfully.")
        else:
            create_employee_stage_path(emp, [], change_reason=change_reason, modified_by=request.user)
            log_activity(request, action="clear_employee_workflow", entity_type="employee", entity_id=emp.id,
                         description="Cleared custom workflow and restored default workflow")
            messages.success(request, "Custom workflow cleared. Default workflow restored.")

    responses = FormResponse.objects.filter(employee=emp).select_related("form")
    medical = MedicalRecord.objects.filter(employee=emp)
    actions = pipeline.review_actions_for(emp.status)
    review_stage = pipeline.stage_of_status(emp.status)
    convo_stage = pipeline.current_stage(emp) or review_stage
    thread = ReviewMessage.objects.filter(employee=emp).select_related("author").order_by("created_at")
    if request.user.role not in ("medical_approver", "super_admin"):
        thread = thread.exclude(stage="medical")
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
    from ..pipeline_v2 import get_employee_stage_path
    from ..models import StageDefinition, StageTemplate

    employee_stage_path = get_employee_stage_path(emp)
    stage_definitions = {s.stage_key: s for s in StageDefinition.objects.filter(is_enabled=True)}
    stage_templates_qs = StageTemplate.objects.filter(is_active=True).order_by("name")
    stages = []
    for idx, stage_key in enumerate(employee_stage_path):
        stage_def = stage_definitions.get(stage_key)
        stages.append({
            "stage_key": stage_key,
            "label": stage_def.label if stage_def else pipeline.STAGE_LABELS.get(stage_key, stage_key.replace("_", " ").title()),
            "order": idx,
            "is_enabled": bool(stage_def),
            "status": pipeline.stage_state(emp, stage_key),
        })
    current_stage_key = pipeline.current_stage(emp)

    stage_progress = {
        'status': emp.stage_status(),
        'days_remaining': emp.days_remaining_in_stage(),
        'due_date': emp.get_effective_due_date(),
        'entered_at': emp.stage_entered_at,
        'is_overdue': emp.is_stage_overdue(),
        'stage_name': pipeline.STAGE_LABELS.get(current_stage_key, current_stage_key or "Not started"),
    }

    # Get unified stages with all activities
    from ..services.unified_stages_service import get_employee_all_stages
    unified_stages = get_employee_all_stages(emp)
    all_stages_qs = StageDefinition.objects.filter(is_enabled=True).order_by("order")

    is_med_approved = pipeline.stage_state(emp, "medical") in ("completed", "approved")
    pct = onboarding_progress_percent(emp.status, emp)
    if request.user.role == "medical_approver":
        unified_stages = [s for s in unified_stages if s['key'] == 'medical']
        if is_med_approved:
            stage_progress['stage_name'] = "Medical Approved"
            stage_progress['status'] = "completed"
            pct = 100

    return render(request, "admin/employee_detail.html", {
        "emp": emp,
        "msg_templates": msg_templates,
        "responses": responses,
        "medical": medical,
        "pct": pct,
        "statuses": EMPLOYEE_STATUSES,
        "review_actions": actions,
        "review_stage_label": pipeline.STAGE_LABELS.get(review_stage, ""),
        "awaiting_review": bool(actions),
        "can_review": _can_review(request.user, emp.status),
        "can_bypass": request.user.has_perm_key("bypass_stages"),
        "stages": stages,
        "stage_progress": stage_progress,
        "offer_status": pipeline.stage_state(emp, "offer") if "offer" in employee_stage_path else "disabled",
        "medical_status": pipeline.stage_state(emp, "medical") if "medical" in employee_stage_path else "disabled",
        "pre_onboarding_status": pipeline.stage_state(emp, "pre_onboarding") if "pre_onboarding" in employee_stage_path else "disabled",
        "onboarding_status": pipeline.stage_state(emp, "onboarding") if "onboarding" in employee_stage_path else "disabled",
        "post_onboarding_status": pipeline.stage_state(emp, "post_onboarding") if "post_onboarding" in employee_stage_path else "disabled",
        "can_on_behalf": request.user.has_perm_key("on_behalf_documents"),
        "current_stage_label": pipeline.STAGE_LABELS.get(current_stage_key, ""),
        "is_onboarding_active": current_stage_key is not None
                                and emp.status not in ("deleted", "on_hold"),
        # Workflow configuration
        "employee_stage_path": employee_stage_path,
        "stage_definitions": stage_definitions,
        "all_stages": all_stages_qs,
        "stage_templates": stage_templates_qs,
        "has_custom_path": emp.stage_path is not None,
        "can_customize_workflow": request.user.has_perm_key("customize_employee_workflow"),
        "thread": thread,
        "convo_stage": convo_stage,
        "convo_stage_label": pipeline.STAGE_LABELS.get(convo_stage, ""),
        "unified_stages": unified_stages,  # All stages with activities
        "is_super_admin": request.user.role == 'super_admin',
        "can_manage_users": request.user.has_perm_key("manage_users"),
        "is_med_approved": is_med_approved,
    })


@staff_required
@require_http_methods(["POST"])
def bulk_delete_employees(request):
    raw_ids = request.POST.getlist("selected_ids")
    selected_ids = []
    for value in raw_ids:
        for item in value.split(","):
            item = item.strip()
            if item.isdigit():
                selected_ids.append(int(item))
    if selected_ids:
        qs = scoped_employee_qs(
            request.user,
            User.objects.filter(id__in=selected_ids, role__in=_employee_role_keys()).exclude(status="deleted"),
        )
        updated = qs.update(status="deleted", is_active=False)
        log_activity(request, action="bulk_delete_employees", entity_type="employee",
                     description=f"Soft-deleted {updated} employee(s)")
        messages.success(request, f"Deleted {updated} selected employee(s).")
    else:
        messages.warning(request, "No employees were selected.")
    return redirect("admin_employees")

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
    emp.is_active = False
    emp.save(update_fields=["status", "is_active"])

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

            elif action == "reconsider_record":
                rec.status = "under_review" if rec.file else "pending"
                rec.reviewed_by = None
                rec.reviewed_at = None
                rec.save(update_fields=["status", "reviewed_by", "reviewed_at"])
                
                # Sync employee status back to medical if they were already advanced
                pipeline.get_employee_stage_path(selected)
                
                log_activity(request, action="reconsider_medical_record", entity_type="employee", entity_id=selected.id,
                             description=f"Reconsidered medical record '{rec.requirement_name}' for {selected.email}")
                messages.success(request, f"Reconsidered '{rec.requirement_name}' — status reset.")

        query = [f"user_id={selected.id}"]
        if keep_filter:
            query.insert(0, "has_submissions=1")
        return redirect(f"{request.path}?{'&'.join(query)}")

    employees_list = list(qs)
    for emp in employees_list:
        med_state = pipeline.stage_state(emp, "medical")
        if med_state in ("completed", "approved"):
            emp.medical_display_status = "Medical Approved"
        else:
            emp.medical_display_status = pipeline.STAGE_LABELS.get(pipeline.stage_of_status(emp.status), emp.status.replace("_", " ").title())

    if selected:
        med_state = pipeline.stage_state(selected, "medical")
        if med_state in ("completed", "approved"):
            selected.medical_display_status = "Medical Approved"
        else:
            selected.medical_display_status = pipeline.STAGE_LABELS.get(pipeline.stage_of_status(selected.status), selected.status.replace("_", " ").title())

    return render(request, "admin/medical_review.html", {
        "employees": employees_list,
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


@permission_required("approve_medical")
@require_http_methods(["GET"])
def export_medical_stats_csv(request):
    """Export medical review statistics for all employees in scope as a CSV."""
    from ..exporters import csv_response
    
    # Get all employees within scope
    qs = scoped_employee_qs(request.user, User.objects.filter(role__in=_employee_role_keys())).exclude(status="deleted").order_by("full_name")
    
    header = [
        "Employee ID", "Full Name", "Email", "Department", "Location", 
        "Overall Medical Status", "Total Requirements", "Submitted", 
        "Approved", "Rejected", "Pending", "Last Updated"
    ]
    
    rows = []
    for emp in qs:
        # Fetch medical records for the employee
        records = MedicalRecord.objects.filter(employee=emp, is_catalog=False)
        total = records.count()
        submitted = records.filter(status="submitted").count()
        approved = records.filter(status="approved").count()
        rejected = records.filter(status="rejected").count()
        pending = records.filter(status="pending").count()
        
        # Calculate last updated
        last_rec = records.order_by("-reviewed_at").first()
        last_updated = last_rec.reviewed_at.strftime("%Y-%m-%d %H:%M") if (last_rec and last_rec.reviewed_at) else "N/A"
        
        # Determine overall medical status
        med_state = pipeline.stage_state(emp, "medical")
        if med_state in ("completed", "approved"):
            overall_status = "Medical Approved"
        else:
            overall_status = med_state.replace("_", " ").title()
            
        rows.append([
            emp.employee_id or "N/A",
            emp.full_name,
            emp.email,
            emp.department.name if emp.department else "N/A",
            emp.location_code or "N/A",
            overall_status,
            total,
            submitted,
            approved,
            rejected,
            pending,
            last_updated
        ])
        
    log_activity(request, action="export_medical_stats", entity_type="employee",
                 description=f"Exported medical stats for {qs.count()} employees")
                 
    return csv_response("medical_onboarding_stats.csv", header, rows)


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
    if stage == "medical" and request.user.role not in ("medical_approver", "super_admin"):
        messages.error(request, "You do not have permission to post medical messages.")
        return redirect("admin_employee_detail", user_id=emp.id)
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

    from ..services.email_service import EmailService, _small_portal_link
    if action == "approve" and stage == "medical":
        EmailService.send_email(to_email=emp.email, template_key="medical_approved", context={"full_name": emp.full_name or emp.email, "small_portal_link_onboarding": _small_portal_link(request.build_absolute_uri("/employee/home/"))})
    elif action == "approve" and stage == "pre_onboarding":
        EmailService.send_email(to_email=emp.email, template_key="pre_onboarding_approved", context={"full_name": emp.full_name or emp.email, "small_portal_link_continue_docs": _small_portal_link(request.build_absolute_uri("/employee/home/"))})
    elif action == "reject" and stage == "medical":
        EmailService.send_email(to_email=emp.email, template_key="medical_rejected", context={"full_name": emp.full_name or emp.email, "remarks_html": f"<p>{note}</p>", "small_portal_link_view": _small_portal_link(request.build_absolute_uri("/employee/home/"))})
    elif action == "reject" and stage == "pre_onboarding":
        EmailService.send_email(to_email=emp.email, template_key="pre_onboarding_rejected", context={"full_name": emp.full_name or emp.email, "reason_html": f"<p>{note}</p>", "small_portal_link_view": _small_portal_link(request.build_absolute_uri("/employee/home/"))})
    elif action == "request_info":
        EmailService.send_email(to_email=emp.email, template_key="info_requested", context={"full_name": emp.full_name or emp.email, "stage_label": pipeline.STAGE_LABELS.get(stage, stage), "question": note, "small_portal_link_respond": _small_portal_link(request.build_absolute_uri("/employee/home/"))})
    elif action == "request_changes":
        EmailService.send_email(to_email=emp.email, template_key="resubmission_requested", context={"full_name": emp.full_name or emp.email, "stage_label": pipeline.STAGE_LABELS.get(stage, stage), "message": note, "small_portal_link_stage": _small_portal_link(request.build_absolute_uri("/employee/home/"))})

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
    sort = (request.GET.get("sort") or "name").strip()
    direction = (request.GET.get("dir") or "asc").strip().lower()
    raw_cols = request.GET.getlist("cols")
    visible_cols = []
    for c in raw_cols:
        if "," in c:
            visible_cols.extend(c.split(","))
        else:
            visible_cols.append(c)
    if not visible_cols:
        visible_cols = ["name", "email", "role", "status", "department", "location"]

    sort_map = {
        "name": "full_name",
        "email": "email",
        "role": "role",
        "status": "is_active",
        "department": "department__name",
        "location": "location_code",
    }

    qs = User.objects.filter(role__in=_staff_role_keys()).exclude(status="deleted").select_related("department")
    order_field = sort_map.get(sort, "full_name")
    if direction == "desc":
        qs = qs.order_by(f"-{order_field}")
    else:
        qs = qs.order_by(order_field)

    from ..models import OrgUnit
    depts_map = {d.id: d.name for d in OrgUnit.objects.filter(kind="department")}
    staff = list(qs)
    for u in staff:
        scope_dept_ids = (u.scope or {}).get("departments") or []
        u.resolved_scope_departments = [depts_map.get(dept_id, f"Dept #{dept_id}") for dept_id in scope_dept_ids]

    return render(request, "admin/users.html", {
        "users": staff,
        "roles": [(r["key"], r["label"]) for r in all_roles()],
        "sort": sort,
        "dir": direction,
        "visible_columns": visible_cols,
        "column_options": [
            ("name", "Name"),
            ("email", "Email"),
            ("role", "Role"),
            ("status", "Status"),
            ("department", "Department / Scope"),
            ("location", "Location / Scope"),
        ],
    })


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
    from ..pipeline_v2 import create_employee_stage_path
    from ..models import StageDefinition

    workflow_choice = request.POST.get("workflow_choice", "default")

    # Get enabled stages for validation
    enabled_stages = set(StageDefinition.objects.filter(is_enabled=True).values_list("stage_key", flat=True))

    if workflow_choice == "template":
        template_name = request.POST.get("template_name")
        # Get template from database - it should already only contain enabled stages
        from ..models import StageTemplate
        try:
            template = StageTemplate.objects.get(name=template_name, is_active=True)
            # Filter template stages to only enabled ones (extra safety)
            valid_stages = [s for s in template.stages if s in enabled_stages]
            if valid_stages:
                create_employee_stage_path(
                    user,
                    stages=valid_stages,
                    change_reason=f"Created with template: {template.name}",
                    modified_by=request.user,
                )
        except StageTemplate.DoesNotExist:
            pass

    elif workflow_choice == "custom":
        custom_stages = request.POST.getlist("custom_stages")
        if custom_stages:
            # Validate: only enabled stages can be assigned
            invalid_stages = set(custom_stages) - enabled_stages
            if invalid_stages:
                # Silently filter out invalid stages (they shouldn't be in the form anyway)
                custom_stages = [s for s in custom_stages if s in enabled_stages]

            if custom_stages:
                create_employee_stage_path(
                    user,
                    stages=custom_stages,
                    change_reason="Created with custom stage selection",
                    modified_by=request.user,
                )
    # else: "default" or not specified - leave stage_path as NULL (uses global defaults)


def _user_form_context(selected_perms=None, **extra):
    from ..models import StageDefinition, StageTemplate
    from ..pipeline_v2 import get_global_default_stages

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
        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            if existing.status == "deleted":
                # Reactivate the soft-deleted user
                existing.status = "pending" if is_employee_role(role) else "completed"
                existing.is_active = True
                existing.role = role
                existing.must_change_password = True
                _apply_user_fields(request, existing)
                temp_password = secrets.token_urlsafe(9)
                existing.set_password(temp_password)
                existing.save()
                _apply_permissions(request, existing)
                existing.save(update_fields=["permissions_override"])
                if is_employee_role(role):
                    _apply_employee_workflow(request, existing)
                    from ..services.email_service import EmailService, _big_login_cta
                    EmailService.send_email(
                        to_email=existing.email,
                        template_key='welcome_employee',
                        context={
                            'full_name': existing.full_name or existing.email,
                            'email': existing.email,
                            'temp_password': temp_password,
                            'big_login_cta': _big_login_cta(request.build_absolute_uri('/login/'))
                        }
                    )
                else:
                    from ..services.email_service import EmailService, _big_login_cta
                    EmailService.send_email(
                        to_email=existing.email,
                        template_key='welcome_admin',
                        context={
                            'full_name': existing.full_name or existing.email,
                            'email': existing.email,
                            'role_label': role.replace('_', ' ').title(),
                            'temp_password': temp_password,
                            'big_login_cta': _big_login_cta(request.build_absolute_uri('/login/'))
                        }
                    )
                log_activity(request, action="reactivate_user", entity_type="user", entity_id=existing.id,
                             description=f"Reactivated deleted {role} {existing.email}")
                messages.success(request, f"Reactivated previously deleted user. Temporary password for {email}: {temp_password}")
                return redirect("admin_edit_user", user_id=existing.id)
            else:
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
            from ..services.email_service import EmailService, _big_login_cta
            EmailService.send_email(
                to_email=user.email,
                template_key='welcome_employee',
                context={
                    'full_name': user.full_name or user.email,
                    'email': user.email,
                    'temp_password': temp_password,
                    'big_login_cta': _big_login_cta(request.build_absolute_uri('/login/'))
                }
            )
        else:
            from ..services.email_service import EmailService, _big_login_cta
            EmailService.send_email(
                to_email=user.email,
                template_key='welcome_admin',
                context={
                    'full_name': user.full_name or user.email,
                    'email': user.email,
                    'role_label': role.replace('_', ' ').title(),
                    'temp_password': temp_password,
                    'big_login_cta': _big_login_cta(request.build_absolute_uri('/login/'))
                }
            )

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
        # Handle email change
        new_email = (request.POST.get("email") or "").strip().lower()
        if new_email and new_email != user.email:
            if User.objects.filter(email__iexact=new_email).exclude(id=user.id).exists():
                messages.error(request, f"Another user already has the email {new_email}.")
                return redirect("admin_edit_user", user_id=user.id)
            user.email = new_email
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
           
    from ..services.email_service import EmailService, _small_portal_link
    EmailService.send_email(
        to_email=user.email, template_key="medical_approved",
        context={"full_name": user.full_name or user.email, "small_portal_link_onboarding": _small_portal_link(request.build_absolute_uri("/employee/home/"))}
    )
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
        kind = request.POST.get("kind") or "department"
        tab = kind if kind in valid_kinds else "department"
        if action == "import_options":
            uploaded_file = request.FILES.get("import_file")
            if not uploaded_file:
                messages.error(request, "Choose a file to import.")
            elif kind not in valid_kinds:
                messages.error(request, "Invalid organization tab selected.")
            else:
                try:
                    rows = _read_org_option_rows(uploaded_file)
                except Exception as exc:  # pragma: no cover - defensive path
                    messages.error(request, f"Import failed: {exc}")
                else:
                    created = 0
                    skipped = 0
                    for row in rows:
                        name = str(row.get("name") or row.get("option_name") or "").strip()
                        if not name:
                            skipped += 1
                            continue
                        if OrgUnit.objects.filter(kind=kind, name__iexact=name, tenant=request.user.tenant).exists():
                            skipped += 1
                            continue
                        OrgUnit.objects.create(
                            kind=kind,
                            name=name,
                            description=str(row.get("description") or "").strip(),
                            tenant=request.user.tenant,
                            is_active=True,
                        )
                        created += 1
                    messages.success(request, f"Imported {created} new {kind} option(s). Skipped {skipped} existing or blank row(s).")
        elif action == "export_options":
            if kind not in valid_kinds:
                messages.error(request, "Invalid organization tab selected.")
            else:
                options = OrgUnit.objects.filter(kind=kind, tenant=request.user.tenant).order_by("name")
                workbook = _build_org_option_export_workbook(kind, options)
                output = io.BytesIO()
                workbook.save(output)
                output.seek(0)
                response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                response["Content-Disposition"] = f'attachment; filename="{kind}_options.xlsx"'
                return response
        elif action == "download_template":
            workbook = _build_org_option_template_workbook(ORG_KINDS)
            output = io.BytesIO()
            workbook.save(output)
            output.seek(0)
            response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            response["Content-Disposition"] = 'attachment; filename="organization_options_template.xlsx"'
            return response
        elif action == "add":
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
                ou.delete()
                messages.success(request, "Option deleted.")
        return redirect(f"{reverse('admin_organization')}?tab={tab}")

    tab = request.GET.get("tab") or "department"
    return render(request, "admin/organization.html", {
        "kinds": ORG_KINDS,
        "options": _org_options(),
        "active_tab": tab,
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
        # Passwords: only overwrite when a new value is provided.
        new_pw = request.POST.get("smtp_password")
        if new_pw:
            AppSetting.set("smtp_password", new_pw, user=request.user)
        
        new_resend = request.POST.get("resend_api_key")
        if new_resend:
            AppSetting.set("resend_api_key", new_resend, user=request.user)
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
    smtp["has_resend_api_key"] = bool(AppSetting.get("resend_api_key"))
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
    import json
    from django.conf import settings as dj_settings
    from .auth_views import LOGIN_SCREEN_DEFAULTS
    
    if request.method == "POST":
        if request.POST.get("action") == "reset":
            AppSetting.objects.filter(
                key__in=list(BRANDING_DEFAULTS) + ["site_logo", "login_screen_settings"]
            ).delete()
            messages.success(request, "Branding reset to defaults.")
            return redirect("admin_branding")
            
        AppSetting.set("site_title", (request.POST.get("site_title") or "").strip(), user=request.user)
        for k in BRANDING_COLOR_KEYS + BRANDING_SELECT_KEYS:
            AppSetting.set(k, (request.POST.get(k) or "").strip(), user=request.user)
            
        # Capture Login Screen Settings
        login_settings = {
            "sync_portal_colors": request.POST.get("login_sync_portal_colors") == "1",
            "background_style": request.POST.get("login_bg_style", "gradient"),
            "primary_color": request.POST.get("login_primary_color", "#1d2b4f"),
            "accent_color": request.POST.get("login_accent_color", "#324b8a"),
            "welcome_title": (request.POST.get("login_welcome_title") or "").strip(),
            "welcome_subtitle": (request.POST.get("login_welcome_subtitle") or "").strip(),
            "show_logo": request.POST.get("login_show_logo") == "1",
        }
        AppSetting.set("login_screen_settings", json.dumps(login_settings), user=request.user)
        
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
        messages.success(request, "Branding saved - the whole portal now reflects your changes.")
        return redirect("admin_branding")

    current = {k: (AppSetting.get(k) or BRANDING_DEFAULTS[k]) for k in BRANDING_DEFAULTS}
    
    # Load custom login settings
    login_settings_raw = AppSetting.get("login_screen_settings")
    login_settings = {}
    if login_settings_raw:
        try:
            login_settings = json.loads(login_settings_raw)
        except Exception:
            pass
            
    for k, v in LOGIN_SCREEN_DEFAULTS.items():
        login_settings.setdefault(k, v)

    return render(request, "admin/branding.html", {
        "b": current,
        "login_settings": login_settings,
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


RESET_CONFIRM_PHRASE = "RESET DATABASE"
PRESERVE_CURRENT_ADMIN_DEFAULT = True


def _portal_reset_summary():
    rows = [
        ("Users", User.objects.count()),
        ("Employees", User.objects.filter(role="employee").count()),
        ("Staff", User.objects.exclude(role="employee").count()),
        ("Departments", OrgUnit.objects.filter(kind="department").count()),
        ("Locations", OrgUnit.objects.filter(kind="location").count()),
        ("Forms", Form.objects.count()),
        ("Form Responses", FormResponse.objects.count()),
        ("Documents", OnboardingDocument.objects.count()),
        ("Medical Records", MedicalRecord.objects.count()),
        ("Content Items", Content.objects.count()),
        ("Engagements", Engagement.objects.count()),
        ("Notifications", Notification.objects.count()),
        ("Audit Logs", AuditLog.objects.count()),
        ("Stage Definitions", StageDefinition.objects.count()),
        ("Stage Templates", StageTemplate.objects.count()),
        ("Employee Stage Paths", EmployeeStagePath.objects.count()),
        ("Offer Workflows", OfferWorkflow.objects.count()),
        ("App Settings", AppSetting.objects.count()),
    ]
    return rows


def _capture_super_admin_snapshot(user):
    return {
        "email": user.email,
        "full_name": user.full_name,
        "password": user.password,
        "phone_number": user.phone_number,
        "employee_id": user.employee_id,
        "role": "super_admin",
        "status": "completed",
        "must_change_password": False,
        "is_staff": True,
        "is_superuser": True,
        "is_active": True,
    }


def _restore_super_admin_snapshot(snapshot):
    if not snapshot:
        return None
    user, _ = User.objects.get_or_create(
        email=snapshot["email"],
        defaults={
            "full_name": snapshot["full_name"],
            "role": snapshot["role"],
            "status": snapshot["status"],
            "must_change_password": snapshot["must_change_password"],
            "is_staff": snapshot["is_staff"],
            "is_superuser": snapshot["is_superuser"],
            "is_active": snapshot["is_active"],
            "phone_number": snapshot.get("phone_number"),
            "employee_id": snapshot.get("employee_id"),
        },
    )
    user.full_name = snapshot["full_name"]
    user.role = snapshot["role"]
    user.status = snapshot["status"]
    user.must_change_password = snapshot["must_change_password"]
    user.is_staff = snapshot["is_staff"]
    user.is_superuser = snapshot["is_superuser"]
    user.is_active = snapshot["is_active"]
    user.phone_number = snapshot.get("phone_number")
    user.employee_id = snapshot.get("employee_id")
    user.tenant = None
    user.password = snapshot["password"]
    user.save()
    return user


def _clear_media_root():
    from django.conf import settings as dj_settings

    media_root = getattr(dj_settings, "MEDIA_ROOT", "")
    if not media_root or not os.path.isdir(media_root):
        return
    for entry in os.listdir(media_root):
        path = os.path.join(media_root, entry)
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


def _wipe_core_data():
    core_models = list(apps.get_app_config("core").get_models())
    # Delete child tables first, leave auth/session tables alone, and remove
    # the current user last so the request can still complete cleanly.
    def sort_key(model):
        name = model._meta.model_name
        if name == "user":
            return (2, name)
        if name == "tenant":
            return (1, name)
        return (0, name)

    for model in sorted(core_models, key=sort_key, reverse=True):
        model.objects.all().delete()


def _perform_portal_reset(preserve_super_admin_snapshot=None):
    summary = _portal_reset_summary()
    _wipe_core_data()
    user = _restore_super_admin_snapshot(preserve_super_admin_snapshot)
    cache.clear()
    _clear_media_root()
    return summary, user


@roles_required("super_admin")
@require_http_methods(["GET", "POST"])
def portal_reset(request):
    summary = _portal_reset_summary()
    if request.method == "POST":
        confirm_phrase = (request.POST.get("confirm_phrase") or "").strip()
        if confirm_phrase != RESET_CONFIRM_PHRASE:
            messages.error(request, f"Type {RESET_CONFIRM_PHRASE} exactly to confirm the reset.")
            return redirect("admin_portal_reset")
        preserve_current = request.POST.get("preserve_current_super_admin") != "off"
        snapshot = _capture_super_admin_snapshot(request.user) if preserve_current else None
        reset_result = _perform_portal_reset(snapshot)
        if isinstance(reset_result, tuple) and len(reset_result) == 2:
            summary, restored_user = reset_result
        else:
            summary, restored_user = reset_result, None
        if restored_user is not None:
            backend = settings.AUTHENTICATION_BACKENDS[0] if settings.AUTHENTICATION_BACKENDS else None
            if backend:
                auth_login(request, restored_user, backend=backend)
        return render(request, "admin/system_reset.html", {
            "reset_complete": True,
            "summary": summary,
            "summary_map": dict(summary),
            "confirm_phrase": RESET_CONFIRM_PHRASE,
            "preserve_current_super_admin": preserve_current,
            "preserved_current_super_admin": preserve_current,
        })
    return render(request, "admin/system_reset.html", {
        "reset_complete": False,
        "summary": summary,
        "summary_map": dict(summary),
        "confirm_phrase": RESET_CONFIRM_PHRASE,
        "preserve_current_super_admin": PRESERVE_CURRENT_ADMIN_DEFAULT,
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
def bulk_delete_users(request):
    raw_ids = request.POST.getlist("selected_ids")
    selected_ids = []
    for value in raw_ids:
        for item in value.split(","):
            item = item.strip()
            if item.isdigit():
                selected_ids.append(int(item))
    if selected_ids:
        updated = User.objects.filter(id__in=selected_ids).exclude(id=request.user.id).exclude(status="deleted").update(status="deleted", is_active=False)
        log_activity(request, action="bulk_delete_users", entity_type="user",
                     description=f"Soft-deleted {updated} user(s)")
        messages.success(request, f"Deleted {updated} selected user(s).")
    else:
        messages.warning(request, "No users were selected.")
    return redirect("admin_users")

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
    if not Form.objects.filter(stage="pre_onboarding").exists():
        # Auto-seed a comprehensive Universal Workflow Form
        Form.objects.create(
            tenant=request.user.tenant,
            name="Universal Pre-Onboarding & Document Sign-Off Package",
            description="Combined Personal Information, Company Code of Conduct Policy E-Signature, and Direct Deposit Setup.",
            stage="pre_onboarding",
            form_kind="form",
            is_active=True,
            display_order=1,
            schema={
                "sections": [
                    {
                        "id": "sec_personal",
                        "title": "1. Personal & Emergency Details",
                        "description": "Please verify your personal contact details.",
                        "fields": [
                            {"id": "f_name", "field_name": "full_name", "label": "Full Legal Name", "field_type": "text", "is_required": True},
                            {"id": "f_phone", "field_name": "phone_number", "label": "Mobile Phone Number", "field_type": "phone", "is_required": True},
                            {"id": "f_dob", "field_name": "date_of_birth", "label": "Date of Birth", "field_type": "date", "is_required": True},
                            {"id": "f_addr", "field_name": "home_address", "label": "Current Residential Address", "field_type": "textarea", "is_required": True},
                            {"id": "f_emg", "field_name": "emergency_contact", "label": "Emergency Contact Name & Phone", "field_type": "text", "is_required": True}
                        ]
                    },
                    {
                        "id": "sec_policy",
                        "title": "2. Code of Conduct & NDA Policy E-Signature",
                        "description": "Please read the policy terms below and sign electronically.",
                        "fields": [
                            {
                                "id": "f_policy",
                                "field_name": "code_of_conduct_policy",
                                "label": "Enterprise Code of Conduct & Non-Disclosure Agreement (NDA)",
                                "field_type": "policy_sign",
                                "is_required": True,
                                "policy_html": "<h4>Code of Conduct & Confidentiality Agreement</h4><p>As an employee of OnboardHub, you agree to maintain the highest standards of integrity, professional conduct, and confidentiality. All proprietary source code, business strategies, and customer data remain strictly confidential.</p><p>By signing below, you acknowledge and agree to abide by these enterprise policies.</p>"
                            }
                        ]
                    },
                    {
                        "id": "sec_banking",
                        "title": "3. Direct Deposit & Bank Details",
                        "description": "Provide your direct deposit bank details for payroll processing.",
                        "fields": [
                            {"id": "f_bname", "field_name": "bank_name", "label": "Bank Name", "field_type": "text", "is_required": True},
                            {"id": "f_routing", "field_name": "routing_number", "label": "Routing Number / IBAN Code", "field_type": "text", "is_required": True},
                            {"id": "f_acct", "field_name": "account_number", "label": "Account Number", "field_type": "text", "is_required": True},
                            {"id": "f_voided", "field_name": "bank_proof_file", "label": "Upload Voided Check / Bank Authorization Letter", "field_type": "file", "is_required": False},
                            {
                                "id": "f_bank_sign",
                                "field_name": "direct_deposit_esignature",
                                "label": "Direct Deposit Authorization Digital E-Signature",
                                "field_type": "policy_sign",
                                "is_required": True,
                                "policy_html": "<p>I authorize OnboardHub to credit direct deposit payroll payments into the bank account specified above.</p>"
                            }
                        ]
                    }
                ]
            }
        )
    forms = Form.objects.all().order_by("stage", "display_order", "id")
    return render(request, "admin/forms.html", {"forms": forms, "stages": STAGE_CHOICES})


@permission_required("manage_forms")
@require_http_methods(["GET", "POST"])
def create_form(request):
    if request.method == "POST":
        form = _save_form_from_post(request, Form())
        messages.success(request, "Form created.")
        return redirect("admin_edit_form", form_id=form.id)
    
    # If a kind was passed in URL (e.g. from Quiz List), pass it to context
    # so the frontend can pre-select Quiz mode.
    default_kind = "quiz" if request.path.startswith("/admin/quizzes/create") else "form"
    
    return render(request, "admin/edit_form.html", {
        "form": None, "stages": STAGE_CHOICES, "schema_json": json.dumps({"sections": []}),
        "default_kind": default_kind
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
    form.is_anonymous = bool(request.POST.get("is_anonymous"))
    form.allow_multiple_submissions = bool(request.POST.get("allow_multiple_submissions"))
    form.show_progress_bar = bool(request.POST.get("show_progress_bar", True))
    form.shuffle_questions = bool(request.POST.get("shuffle_questions"))

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

    # Attach enterprise settings to schema
    settings_dict = schema.setdefault("settings", {})
    try:
        settings_dict["passing_score"] = float(request.POST.get("passing_score") or 80.0)
    except ValueError:
        settings_dict["passing_score"] = 80.0

    try:
        settings_dict["max_attempts"] = int(request.POST.get("max_attempts") or 0)
    except ValueError:
        settings_dict["max_attempts"] = 0

    try:
        settings_dict["time_limit_minutes"] = int(request.POST.get("time_limit_minutes") or 0)
    except ValueError:
        settings_dict["time_limit_minutes"] = 0

    assigned_roles = request.POST.getlist("assigned_roles")
    settings_dict["assigned_roles"] = [r.strip() for r in assigned_roles if r.strip()]
    
    # Process attached document uploads for signable document items (pdf_sign, doc_sign, ppt_view)
    if request.FILES:
        from django.core.files.storage import default_storage
        for key, uploaded_file in request.FILES.items():
            if key.startswith("doc_file_"):
                field_id = key.replace("doc_file_", "")
                saved_path = default_storage.save(f"forms/documents/{uploaded_file.name}", uploaded_file)
                # Find field in schema and attach file_url
                for sec in schema.get("sections", []):
                    for f in sec.get("fields", []):
                        if str(f.get("id")) == str(field_id):
                            f["file_url"] = f"/{saved_path}"

    form.schema = schema

    if form.is_anonymous or request.POST.get("generate_share") or not form.share_token:
        form.generate_share_token()
    if form.tenant_id is None:
        form.tenant = request.user.tenant
    form.save()
    log_activity(request, action="save_form", entity_type="form", entity_id=form.id,
                 description=f"Saved {form.form_kind} '{form.name}'")
    return form


@permission_required("manage_forms")
def form_analytics_view(request, form_id):
    """Enterprise Analytics & Response Breakdown for Forms, Quizzes, and Surveys."""
    from ..models import Form, FormResponse
    form = get_object_or_404(Form, id=form_id)
    responses = form.responses.select_related("employee").order_by("-submitted_at")
    total_responses = responses.count()

    settings_dict = form.schema.get("settings", {})
    passing_score = settings_dict.get("passing_score", 80.0)

    # Score stats for quizzes
    scores = [r.score for r in responses if r.score is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    passed_count = sum(1 for s in scores if s >= passing_score)
    failed_count = sum(1 for s in scores if s < passing_score)
    pass_rate = round((passed_count / len(scores)) * 100, 1) if scores else 0

    # Per-question response breakdown
    all_fields = form.get_all_fields()
    question_stats = []

    for field in all_fields:
        fname = field.get("field_name")
        ftype = field.get("field_type")
        label = field.get("label", fname)
        options = field.get("options") or []

        field_stat = {
            "field_name": fname,
            "label": label,
            "field_type": ftype,
            "total_answers": 0,
            "option_counts": {},
            "text_samples": []
        }

        if ftype in ("radio", "select", "checkbox", "rating", "nps", "likert"):
            for opt in options:
                opt_str = opt.get("label") if isinstance(opt, dict) else str(opt)
                field_stat["option_counts"][opt_str] = 0

        for r in responses:
            ans = (r.answers or {}).get(fname)
            if ans is not None and ans != "":
                field_stat["total_answers"] += 1
                if ftype in ("radio", "select", "rating", "nps") and str(ans) in field_stat["option_counts"]:
                    field_stat["option_counts"][str(ans)] += 1
                elif ftype == "checkbox" and isinstance(ans, list):
                    for item in ans:
                        if str(item) in field_stat["option_counts"]:
                            field_stat["option_counts"][str(item)] += 1
                elif len(field_stat["text_samples"]) < 10:
                    field_stat["text_samples"].append(str(ans))

        question_stats.append(field_stat)

    return render(request, "admin/form_analytics.html", {
        "form": form,
        "responses": responses,
        "total_responses": total_responses,
        "avg_score": avg_score,
        "pass_rate": pass_rate,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "passing_score": passing_score,
        "question_stats": question_stats,
    })


@permission_required("manage_forms")
@require_http_methods(["POST"])
def toggle_form_active(request, form_id):
    """Toggle active/inactive status of a form, quiz, or survey."""
    form = get_object_or_404(Form, id=form_id)
    form.is_active = not form.is_active
    form.save(update_fields=["is_active"])
    status_str = "activated" if form.is_active else "deactivated"
    log_activity(request, action="toggle_form", entity_type="form", entity_id=form.id,
                 description=f"{status_str.title()} form '{form.name}'")
    messages.success(request, f"Project '{form.name}' has been {status_str}.")
    return redirect("admin_forms")


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


def _normalize_medical_requirement_row(row):
    def _lookup(*candidates):
        normalized = {}
        for key, value in row.items():
            if key is None:
                continue
            normalized[str(key).strip().lower().replace(" ", "_").replace("-", "_")] = value
        for candidate in candidates:
            key = str(candidate).strip().lower().replace(" ", "_").replace("-", "_")
            if key in normalized:
                return normalized[key]
        return None

    def _normalize_bool(value):
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"1", "y", "yes", "true", "t", "on"}:
            return True
        if text in {"0", "n", "no", "false", "f", "off", ""}:
            return False
        return None

    gender = _lookup("gender", "applies_to_gender", "applies_gender", "target_gender")
    if isinstance(gender, str):
        gender = gender.strip().lower()
        if gender in {"male", "m"}:
            gender = "male"
        elif gender in {"female", "f"}:
            gender = "female"
        elif gender in {"other", "o", "everyone", "all", "any"}:
            gender = ""
        else:
            gender = ""
    else:
        gender = ""

    min_age = _lookup("min_age", "minimum_age", "age")
    if isinstance(min_age, str):
        min_age = min_age.strip()
        if min_age.isdigit():
            min_age = int(min_age)
        else:
            min_age = None
    elif isinstance(min_age, (int, float)):
        min_age = int(min_age)
    else:
        min_age = None

    return {
        "requirement_name": str(_lookup("requirement_name", "name", "requirement", "test_name") or "").strip(),
        "description": str(_lookup("description", "details", "notes") or "").strip(),
        "gender": gender,
        "min_age": min_age,
        "is_required": _normalize_bool(_lookup("is_required", "required")),
        "is_active": _normalize_bool(_lookup("is_active", "active")),
    }


def _read_medical_requirement_rows(uploaded_file):
    file_name = (getattr(uploaded_file, "name", "") or "").lower()
    uploaded_file.seek(0)

    if file_name.endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(uploaded_file.read().decode("utf-8-sig"))))
        return [_normalize_medical_requirement_row(row) for row in rows]

    if file_name.endswith(".xlsx"):
        workbook = load_workbook(uploaded_file, data_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
        parsed_rows = []
        for row_values in rows[1:]:
            row_data = {}
            for index, header in enumerate(headers):
                if index < len(row_values):
                    row_data[header] = row_values[index]
            parsed_rows.append(_normalize_medical_requirement_row(row_data))
        return parsed_rows

    raise ValueError("Please upload an .xlsx or .csv file.")


def _build_medical_requirement_meta(request_data):
    meta = {}
    gender = (request_data.get("gender") or "").strip().lower()
    if gender in ("male", "female"):
        meta["gender"] = gender
    min_age = (request_data.get("min_age") or "").strip()
    if min_age.isdigit():
        meta["min_age"] = int(min_age)
    return meta


def _read_org_option_rows(uploaded_file):
    file_name = (getattr(uploaded_file, "name", "") or "").lower()
    uploaded_file.seek(0)

    if file_name.endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(uploaded_file.read().decode("utf-8-sig"))))
        return rows

    if file_name.endswith(".xlsx"):
        workbook = load_workbook(uploaded_file, data_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
        parsed_rows = []
        for row_values in rows[1:]:
            row_data = {}
            for index, header in enumerate(headers):
                if index < len(row_values):
                    row_data[header] = row_values[index]
            parsed_rows.append(row_data)
        return parsed_rows

    raise ValueError("Please upload an .xlsx or .csv file.")


def _build_org_option_template_workbook(kinds):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Organization Options"
    sheet.append(["kind", "name", "description"])
    for kind, label in kinds:
        sheet.append([kind, f"Example {label}", f"Sample {label} entry"])
    return workbook


def _build_org_option_export_workbook(kind, options):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Organization Options"
    sheet.append(["kind", "name", "description"])
    for option in options:
        sheet.append([kind, option.name, option.description or ""])
    return workbook


def _build_medical_requirement_template_workbook():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Medical Requirements"
    sheet.append([
        "requirement_name", "description", "gender", "min_age", "is_required",
        "is_active"
    ])
    sheet.append([
        "Blood Test", "Annual screening", "Female", "40", "Yes", "Yes"
    ])
    return workbook


def _build_medical_requirement_export_workbook(catalog):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Medical Requirements"
    sheet.append([
        "requirement_name", "description", "gender", "min_age", "is_required",
        "is_active"
    ])
    for record in catalog:
        meta = record.meta or {}
        sheet.append([
            record.requirement_name,
            record.description or "",
            meta.get("gender", ""),
            meta.get("min_age", ""),
            "Yes" if record.is_required else "No",
            "Yes" if record.is_active else "No",
        ])
    return workbook


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
                meta=_build_medical_requirement_meta(request.POST),
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
            rec.meta = _build_medical_requirement_meta(request.POST)
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
        elif action == "import_requirements":
            uploaded_file = request.FILES.get("import_file")
            if not uploaded_file:
                messages.error(request, "Please choose an Excel file to import.")
            else:
                try:
                    rows = _read_medical_requirement_rows(uploaded_file)
                except Exception as exc:  # pragma: no cover - defensive path
                    messages.error(request, f"Import failed: {exc}")
                else:
                    created = 0
                    updated = 0
                    for row in rows:
                        if not row.get("requirement_name"):
                            continue
                        defaults = {
                            "description": row.get("description") or "",
                            "is_required": row.get("is_required") if row.get("is_required") is not None else True,
                            "is_active": row.get("is_active") if row.get("is_active") is not None else True,
                            "meta": {
                                key: value for key, value in {
                                    "gender": row.get("gender") or "",
                                    "min_age": row.get("min_age"),
                                }.items() if value not in {None, ""}
                            },
                            "tenant": request.user.tenant,
                        }
                        rec, created_flag = MedicalRecord.objects.get_or_create(
                            tenant=request.user.tenant,
                            requirement_name=row["requirement_name"],
                            is_catalog=True,
                            defaults=defaults,
                        )
                        if created_flag:
                            created += 1
                        else:
                            rec.description = defaults["description"]
                            rec.is_required = defaults["is_required"]
                            rec.is_active = defaults["is_active"]
                            rec.meta = defaults["meta"]
                            rec.save(update_fields=["description", "is_required", "is_active", "meta"])
                            updated += 1
                    messages.success(request, f"Imported {created} new requirement(s) and updated {updated} existing requirement(s).")
        elif action == "export_requirements":
            catalog = MedicalRecord.objects.filter(is_catalog=True).order_by("requirement_name")
            workbook = _build_medical_requirement_export_workbook(catalog)
            output = io.BytesIO()
            workbook.save(output)
            output.seek(0)
            response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            response["Content-Disposition"] = 'attachment; filename="medical_requirements.xlsx"'
            return response
        elif action == "download_template":
            workbook = _build_medical_requirement_template_workbook()
            output = io.BytesIO()
            workbook.save(output)
            output.seek(0)
            response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            response["Content-Disposition"] = 'attachment; filename="medical_requirements_template.xlsx"'
            return response
        return redirect("admin_medical_requirements")

    catalog = MedicalRecord.objects.filter(is_catalog=True).order_by("requirement_name")
    return render(request, "admin/medical_requirements.html", {
        "catalog": catalog,
    })


@permission_required("send_offer")
def admin_offer_pdf_export(request, offer_id):
    """Admin endpoint to download single offer as PDF."""
    from ..models_offers import Offer
    from ..services.pdf_service import generate_offer_pdf_response
    offer = get_object_or_404(Offer, id=offer_id)
    if request.user.tenant and offer.tenant_id != request.user.tenant.id:
        return HttpResponseForbidden("Not authorized")
    return generate_offer_pdf_response(offer)


@permission_required("send_offer")
def offers_bulk_zip_export_view(request):
    """Export all offers (or filtered list) as a ZIP archive containing individual PDF documents."""
    import zipfile
    import io
    from ..models_offers import Offer
    from ..services.pdf_service import render_html_to_pdf

    offers = Offer.objects.filter(tenant=request.user.tenant) if request.user.tenant else Offer.objects.all()
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for offer in offers:
            html = offer.rendered_html or f"<h1>Offer {offer.offer_number}</h1><p>Candidate: {offer.candidate_name}</p>"
            pdf_bytes = render_html_to_pdf(html)
            filename = f"Offer_{offer.offer_number}_{offer.candidate_name.replace(' ', '_')}.pdf"
            zf.writestr(filename, pdf_bytes)

    zip_buffer.seek(0)
    filename = f"Offers_Export_{timezone.now():%Y%m%d_%H%M%S}.zip"
    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
