"""Reusable CSV export helpers.

Designed to be embedded anywhere: pass a queryset/objects, get a downloadable
CSV. `export_form_responses` works for any Form (onboarding form, quiz, survey),
so future modules reuse it directly.
"""
import csv

from django.http import HttpResponse
from django.utils import timezone

from .models import FormResponse, OnboardingDocument, MedicalRecord
from .services import onboarding_progress_percent


def _dt(value):
    if not value:
        return ""
    try:
        return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(value)


def csv_response(filename, header, rows):
    """Build a downloadable CSV HttpResponse from a header + row iterable (Excel compatible)."""
    resp = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.write('\ufeff')  # UTF-8 BOM for Microsoft Excel compatibility
    writer = csv.writer(resp)
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if c is None else c for c in row])
    return resp


# ── Employee / user summaries ────────────────────────────────────────────────
EMPLOYEE_HEADER = [
    "Employee ID", "Full Name", "Email", "Status", "Department", "Designation",
    "Grade", "Location", "Payroll", "Employee Type", "Gender", "Date of Birth",
    "Date of Joining", "Progress %", "Created",
]


def employee_rows(qs):
    for u in qs:
        yield [
            u.employee_id, u.full_name, u.email, u.get_status_display(),
            u.department.name if u.department else "",
            u.position_title, u.grade, u.location_code, u.payroll, u.employee_type,
            u.gender, u.date_of_birth, u.date_of_joining,
            onboarding_progress_percent(u.status, u), _dt(u.created_at),
        ]


USER_HEADER = ["Full Name", "Email", "Role", "Status", "Phone", "Department", "Created"]


def user_rows(qs):
    for u in qs:
        yield [u.full_name, u.email, u.get_role_display(), u.get_status_display(),
               u.phone_number, u.department.name if u.department else "", _dt(u.created_at)]


# ── Full per-employee onboarding export (forms + signatures + medical, dated) ──
EMPLOYEE_DETAIL_HEADER = ["Section", "Item", "Value", "Status", "Date"]


def employee_detail_rows(emp):
    # Profile block
    profile = [
        ("Full Name", emp.full_name), ("Email", emp.email),
        ("Employee ID", emp.employee_id or ""), ("Role", emp.get_role_display()),
        ("Status", emp.get_status_display()),
        ("Department", emp.department.name if emp.department else ""),
        ("Designation", emp.position_title or ""), ("Grade", emp.grade or ""),
        ("Location", emp.location_code or ""), ("Employee Type", emp.employee_type or ""),
        ("Date of Joining", emp.date_of_joining or ""),
    ]
    for item, val in profile:
        yield ["Profile", item, val, "", ""]

    # Form responses (answers flattened, with submitted/draft + date)
    for resp in FormResponse.objects.filter(employee=emp).select_related("form").order_by("form__stage"):
        section = f"Form: {resp.form.name} ({resp.form.stage})"
        state = "Draft" if resp.is_draft else "Submitted"
        date = _dt(resp.submitted_at)
        answers = resp.answers or {}
        if not answers:
            yield [section, "(no answers)", "", state, date]
        for key, val in answers.items():
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            yield [section, key, val, state, date]

    # Signed onboarding documents (with signature date)
    for doc in OnboardingDocument.objects.filter(is_active=True):
        sig = next((s for s in (doc.signatures or []) if s.get("employee_id") == emp.id), None)
        if sig:
            yield ["Document Signed", doc.title, doc.stage, "Signed", _dt_iso(sig.get("signed_at"))]

    # Medical records (status + review date)
    for m in MedicalRecord.objects.filter(employee=emp).order_by("requirement_name"):
        yield ["Medical", m.requirement_name, m.review_notes or "",
               m.get_status_display(), _dt(m.reviewed_at)]


def _dt_iso(iso_string):
    """Format an ISO timestamp stored in JSON (signatures) for display."""
    if not iso_string:
        return ""
    try:
        from datetime import datetime
        return datetime.fromisoformat(iso_string).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(iso_string)


# ── Generic form-response export (forms, quizzes, surveys) ────────────────────
def export_form_responses(form):
    """Return (header, rows) for every response to a form. Reusable for quizzes."""
    fields = form.get_all_fields()
    field_names = [f["field_name"] for f in fields]
    labels = [f.get("label") or f["field_name"] for f in fields]

    header = ["Respondent", "Email", "Submitted At", "State"]
    if form.form_kind == "quiz":
        header.append("Score")
    header += labels

    rows = []
    for r in form.responses.select_related("employee").order_by("submitted_at"):
        who = r.employee.full_name if r.employee else (r.respondent_name or "Anonymous")
        email = r.employee.email if r.employee else (r.respondent_email or "")
        base = [who, email, _dt(r.submitted_at), "Draft" if r.is_draft else "Submitted"]
        if form.form_kind == "quiz":
            base.append(r.score if r.score is not None else "")
        answers = r.answers or {}
        for name in field_names:
            val = answers.get(name, "")
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            base.append(val)
        rows.append(base)
    return header, rows
