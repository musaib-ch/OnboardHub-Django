"""Employee-facing onboarding flow (strict sequential pipeline)."""
import os

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .. import pipeline
from ..decorators import login_required
from ..medical_match import auto_map_filename, allowed_medical_file, medical_applicability
from ..models import Form, FormResponse, OnboardingDocument, MedicalRecord, ReviewMessage, Engagement, Content
from ..permissions import is_employee_role
from ..services import onboarding_progress_percent, log_activity, models_q_employee_type, notify
from ..services.onboarding_plan_service import OnboardingPlanService

STAGE_URL = {
    "offer": "my_offers",
    "medical": "employee_medical",
    "pre_onboarding": "employee_pre_onboarding",
    "onboarding": "employee_onboarding",
    "post_onboarding": "employee_post_onboarding",
}
STAGE_TITLES = {
    "offer": "Offer Acceptance",
    "medical": "Medical Clearance",
    "pre_onboarding": "Pre-Onboarding Forms",
    "onboarding": "Onboarding Documents",
    "post_onboarding": "Post-Onboarding",
}
STAGE_DESC = {
    "offer": "Review and accept your offer letter.",
    "medical": "Upload and complete medical requirements.",
    "pre_onboarding": "Submit forms and supporting details.",
    "onboarding": "Review and sign onboarding documents.",
    "post_onboarding": "Complete final forms and close onboarding.",
}


def _employee_only(request):
    if not is_employee_role(request.user.role):
        return redirect("admin_dashboard")
    return None


def _maybe_start_pipeline(user):
    """A brand-new (pending) employee with a joining date enters the first stage."""
    if user.status == "pending" and user.date_of_joining:
        user.status = pipeline.entry_status_for_user(user)
        user.save(update_fields=["status"])


def _gate(request, stage):
    """Show status page if stage isn't accessible at the employee's current point."""
    state = pipeline.stage_state(request.user, stage)
    if state == "disabled":
        messages.info(request, f"{pipeline.STAGE_LABELS[stage]} is not part of your onboarding.")
        return redirect("employee_home")
    if state == "locked":
        # Show locked stage page instead of just redirecting
        return _show_stage_locked(request, stage)
    return None


def _show_stage_locked(request, requested_stage):
    """Show a status page explaining why the stage is locked."""
    user = request.user

    # Get all stages info
    stage_path = [st for st in pipeline.get_employee_stage_path(user) if st in STAGE_URL]
    if not stage_path:
        stage_path = pipeline.enabled_stages()
    stages_info = [{
        "key": st,
        "label": pipeline.STAGE_LABELS[st],
        "desc": STAGE_DESC.get(st, ""),
        "state": pipeline.stage_state(user, st),
        "url_name": STAGE_URL.get(st),
    } for st in stage_path]

    # Use current_stage which properly determines the active stage
    current_stage = pipeline.current_stage(user)
    current_stage_url = STAGE_URL.get(current_stage) if current_stage else None

    return render(request, "employee/stage_locked.html", {
        "status": user.status,
        "current_stage": current_stage,
        "current_stage_label": pipeline.STAGE_LABELS.get(current_stage) if current_stage else "Onboarding",
        "current_stage_url": current_stage_url,
        "requested_stage": requested_stage,
        "requested_stage_label": pipeline.STAGE_LABELS.get(requested_stage),
        "stages_info": stages_info,
        "pct": onboarding_progress_percent(user.status, user),
    })


@login_required
def home(request):
    redir = _employee_only(request)
    if redir:
        return redir
    user = request.user
    # Show dashboard even without joining date - let employee see their progress
    # Only redirect if they're on_hold status
    if user.status == "on_hold":
        return redirect("employee_on_hold")
    # Auto-start pipeline if they have a joining date
    if user.date_of_joining:
        _maybe_start_pipeline(user)

    stage_path = [st for st in pipeline.get_employee_stage_path(user) if st in STAGE_URL]
    if not stage_path:
        stage_path = pipeline.enabled_stages()
    stages_info = [{
        "key": st,
        "label": pipeline.STAGE_LABELS[st],
        "desc": STAGE_DESC[st],
        "state": pipeline.stage_state(user, st),
        "url_name": STAGE_URL[st],
    } for st in stage_path]

    learn_qs = Engagement.objects.filter(user=user, kind="enrollment",
                                         content__kind="learning_path")
    learning = {
        "active": learn_qs.exclude(status="completed").count(),
        "completed": learn_qs.filter(status="completed").count(),
        "overdue": learn_qs.exclude(status="completed").filter(
            due_date__lt=timezone.now().date()).count(),
    }

    # Next task for Phase 1 progress display
    next_task = None
    if user.status != "completed":
        current_stage_key = pipeline.current_stage(user)
        if current_stage_key:
            next_task = {
                "label": pipeline.STAGE_LABELS.get(current_stage_key, "Next Stage"),
                "due_date": user.get_effective_due_date(),
            }

    current_stage = pipeline.current_stage(user)
    ctx = {
        "status": user.status,
        "pct": onboarding_progress_percent(user.status, user),
        "stages_info": stages_info,
        "current_stage": current_stage,
        "current_stage_label": pipeline.STAGE_LABELS.get(current_stage, "Not started"),
        "current_stage_state": pipeline.stage_state(user, current_stage) if current_stage else "pending",
        "learning": learning,
        "next_task": next_task,
        "success_plan": OnboardingPlanService.get_plan_context(user),
        "stage_path": stage_path,
    }
    return render(request, "employee/home.html", ctx)


@login_required
@require_http_methods(["GET", "POST"])
def set_joining_date(request):
    redir = _employee_only(request)
    if redir:
        return redir
    user = request.user
    # Prevent setting the joining date until medical clearance is approved
    if "medical" in pipeline.get_employee_stage_path(user) and pipeline.stage_state(user, "medical") != "completed":
        messages.info(request, "Complete your medical clearance before selecting a joining date.")
        return redirect("employee_medical")
    if request.method == "POST":
        doj = request.POST.get("date_of_joining")
        if not doj:
            messages.error(request, "Please choose your joining date.")
            return redirect("employee_set_joining_date")
        user.date_of_joining = doj
        if user.status == "pending":
            user.status = pipeline.entry_status_for_user(user)
        user.save(update_fields=["date_of_joining", "status"])
        messages.success(request, "Joining date saved.")
        return redirect("employee_home")
    return render(request, "employee/set_joining_date.html")


@login_required
def on_hold(request):
    return render(request, "employee/on_hold.html")


# ── Medical (upload + submit) ────────────────────────────────────────────────
@login_required
@require_http_methods(["GET", "POST"])
def medical(request):
    redir = _employee_only(request)
    if redir:
        return redir
    user = request.user
    _maybe_start_pipeline(user)
    gated = _gate(request, "medical")
    if gated:
        return gated

    state = pipeline.stage_state(user, "medical")
    editable = state in pipeline.EDITABLE_STATES

    # Materialise per-employee records from the catalog, applying age/gender
    # applicability. Conditional tests (PSA/CA-125) appear only when they could
    # apply, and are marked optional when age/gender is unknown.
    emp_records = {r.requirement_name: r for r in MedicalRecord.objects.filter(employee=user)}
    for c in MedicalRecord.objects.filter(is_catalog=True):
        applies, required, _note = medical_applicability(user, c.meta)
        applies = applies and c.is_active
        rec = emp_records.get(c.requirement_name)
        if applies:
            if rec is None:
                completed = state == "completed"
                MedicalRecord.objects.create(
                    employee=user, requirement_name=c.requirement_name,
                    description=c.description, is_required=required, meta=c.meta,
                    status="approved" if completed else "pending",
                    reviewed_at=timezone.now() if completed else None,
                    tenant=user.tenant,
                )
            elif not rec.file and (rec.is_required != required or rec.meta != c.meta):
                rec.is_required = required
                rec.meta = c.meta
                rec.save(update_fields=["is_required", "meta"])
        elif rec is not None and not rec.file:
            rec.delete()  # no longer applicable (and nothing uploaded yet)

    if state == "completed":
        MedicalRecord.objects.filter(
            employee=user,
            is_catalog=False,
            status__in=["pending", "uploaded", "under_review", "rejected", "info_requested"],
        ).update(status="approved", reviewed_at=timezone.now())

    if request.method == "POST" and editable:
        action = request.POST.get("action")
        if action == "bulk_upload":
            return _handle_bulk_medical(request, user)
        if action == "upload":
            rec = get_object_or_404(MedicalRecord, id=request.POST.get("record_id"),
                                    employee=user)
            upload = request.FILES.get("file")
            if upload:
                rec.file = upload
                rec.status = "uploaded"
                rec.review_notes = ""
                rec.save()
                messages.success(request, f"Uploaded document for “{rec.requirement_name}”.")
            else:
                messages.error(request, "Please choose a file to upload.")
            return redirect("employee_medical")
        if action == "submit_stage":
            recs = list(MedicalRecord.objects.filter(employee=user))
            missing = [r for r in recs if r.is_required and not r.file]
            if missing:
                messages.error(request, "Upload all required documents before submitting.")
                return redirect("employee_medical")
            user.status = pipeline.SUBMIT_STATUS["medical"]
            user.save(update_fields=["status"])
            for r in recs:
                if r.file and r.status in ("uploaded", "pending"):
                    r.status = "under_review"
                    r.save(update_fields=["status"])
            log_activity(request, action="submit_medical", entity_type="employee",
                         entity_id=user.id, description="Submitted medical documents for review")
            messages.success(request, "Medical documents submitted for review.")
            
            from ..services.email_service import EmailService, _small_portal_link
            from ..models import User
            admins = User.objects.filter(role__in=["super_admin", "admin"], is_active=True)
            if user.tenant_id:
                admins = admins.filter(tenant_id=user.tenant_id)
            for admin in admins:
                EmailService.send_email(
                    to_email=admin.email,
                    template_key="medical_submitted",
                    context={
                        "employee_name": user.full_name or user.email,
                        "employee_email": user.email,
                        "small_portal_link_review": _small_portal_link(request.build_absolute_uri(f"/admin/medical-review/?user_id={user.id}"))
                    }
                )
            return redirect("employee_medical")

    records = list(MedicalRecord.objects.filter(employee=user))
    # Pending (no file) first; attached/uploaded ones drop to the bottom.
    records.sort(key=lambda r: (bool(r.file), r.requirement_name.lower()))
    for r in records:
        r.applicability_note = medical_applicability(user, r.meta)[2]
    can_submit = all(r.file for r in records if r.is_required) and bool(records)
    missing_required = [r.requirement_name for r in records if r.is_required and not r.file]
    return render(request, "employee/medical.html", {
        "records": records,
        "editable": editable,
        "can_submit": can_submit,
        "missing_required": missing_required,
        "state": state,
        "status": user.status,
    })


def _handle_bulk_medical(request, user):
    """Consolidated upload: drop many files at once, auto-attach each to its test."""
    files = request.FILES.getlist("files")
    if not files:
        messages.error(request, "Please choose one or more files to upload.")
        return redirect("employee_medical")

    recs_by_name = {r.requirement_name: r for r in MedicalRecord.objects.filter(employee=user)}
    matched, unmatched, invalid = [], [], []

    for f in files:
        if not allowed_medical_file(f.name):
            invalid.append(f.name)
            continue
        requirement = auto_map_filename(f.name)
        rec = recs_by_name.get(requirement) if requirement else None
        if rec is None:
            unmatched.append(f.name)
            continue
        rec.file = f
        rec.status = "uploaded"
        rec.review_notes = ""
        rec.save()
        matched.append((f.name, requirement))

    if matched:
        detail = ", ".join(f"{name} → {req}" for name, req in matched)
        messages.success(request, f"Matched {len(matched)} file(s): {detail}")
        log_activity(request, action="bulk_medical_upload", entity_type="employee",
                     entity_id=user.id, description=f"Bulk-uploaded {len(matched)} medical document(s)")
    if invalid:
        messages.error(request, "Unsupported file type (allowed: PDF, JPG, PNG): "
                       + ", ".join(invalid))
    if unmatched:
        messages.warning(
            request,
            "Couldn't auto-detect the test for: " + ", ".join(unmatched)
            + ". Rename the file to include the test name (e.g. \"cbc.pdf\") or upload it "
              "under the right test below.",
        )

    still_missing = [r.requirement_name for r in MedicalRecord.objects.filter(employee=user)
                     if r.is_required and not r.file]
    if still_missing:
        messages.info(request, "Still needed: " + ", ".join(still_missing))

    return redirect("employee_medical")


# ── Generic form/document stage (pre / onboarding / post) ────────────────────
def _stage_view(request, stage, template):
    redir = _employee_only(request)
    if redir:
        return redir
    user = request.user
    _maybe_start_pipeline(user)
    gated = _gate(request, stage)
    if gated:
        return gated

    is_editable = pipeline.is_editable(user, stage)
    if stage == "onboarding" and is_editable and _onboarding_locked(user):
        is_editable = False

    forms = list(
        Form.objects.filter(stage=stage, is_active=True)
        .filter(models_q_employee_type(user))
        .order_by("display_order", "id")
    )
    responses = {
        r.form_id: r for r in FormResponse.objects.filter(employee=user, form__stage=stage)
    }
    docs = list(OnboardingDocument.objects.filter(stage=stage, is_active=True))

    if request.method == "POST":
        return _handle_stage_post(request, stage, forms, responses, docs, is_editable)

    form_blocks = []
    forms_complete = True
    for f in forms:
        resp = responses.get(f.id)
        answers = resp.answers if resp else {}
        files = resp.files if resp else {}
        complete = bool(resp) and not resp.is_draft
        if f.required_field_names() and not _required_satisfied(f, answers, files):
            complete = False
        if not complete:
            forms_complete = False
        form_blocks.append({
            "form": f, "answers": answers, "files": files,
            "saved": bool(resp) and not resp.is_draft,
            "draft": bool(resp) and resp.is_draft,
        })

    signed_doc_ids = [d.id for d in docs if d.signed_by(user.id)]
    required_docs_signed = all(d.signed_by(user.id) for d in docs if d.is_required)

    assigned_content = list(
        Content.objects.filter(kind__in=["training", "orientation", "presentation"], is_active=True)
        .order_by("category", "display_order", "-created_at")
    )
    assigned_content = [
        item for item in assigned_content
        if (item.meta or {}).get("attach_to") and stage in ((item.meta or {}).get("attach_to") or [])
    ]

    thread = ReviewMessage.objects.filter(employee=user).select_related("author").order_by("created_at")
    last_msg = (ReviewMessage.objects.filter(employee=user, author__isnull=False)
                .exclude(author=user).order_by("-created_at").first())
    last_reviewer_id = last_msg.author_id if last_msg else (user.created_by_id or 1)

    ctx = {
        "stage": stage,
        "stage_title": STAGE_TITLES.get(stage, "Onboarding"),
        "status": user.status,
        "state": pipeline.stage_state(user, stage),
        "is_editable": is_editable,
        "form_blocks": form_blocks,
        "forms": forms,
        "docs": docs,
        "signed_doc_ids": signed_doc_ids,
        "forms_complete": forms_complete,
        "required_docs_signed": required_docs_signed,
        "all_done": is_editable and forms_complete and required_docs_signed,
        "onboarding_locked": stage == "onboarding" and _onboarding_locked(user),
        "thread": thread,
        "last_reviewer_id": last_reviewer_id,
        "assigned_content": assigned_content,
    }
    return render(request, template, ctx)


def _handle_stage_post(request, stage, forms, responses, docs, is_editable):
    user = request.user
    action = request.POST.get("action", "")

    # Replying to the reviewer is allowed whenever there's a conversation,
    # regardless of whether the forms are currently editable.
    if action == "send_message":
        text = (request.POST.get("message") or "").strip()
        if text:
            ReviewMessage.objects.create(employee=user, stage=stage, author=user,
                                         message=text, kind="reply")
            last_rev = (ReviewMessage.objects
                        .filter(employee=user, author__isnull=False)
                        .exclude(author=user).order_by("-created_at").first())
            if last_rev and last_rev.author:
                notify(last_rev.author, f"{user.full_name} replied",
                       text, link=f"/admin/employees/{user.id}/", category="info")
            messages.success(request, "Reply sent.")
        return redirect(request.path)

    if not is_editable:
        messages.error(request, "This stage is read-only right now.")
        return redirect(request.path)

    if action == "sign_document":
        doc = get_object_or_404(OnboardingDocument, id=request.POST.get("doc_id"), stage=stage)
        if not doc.signed_by(user.id):
            doc.signatures.append({"employee_id": user.id,
                                   "signed_at": timezone.now().isoformat()})
            doc.save(update_fields=["signatures"])
            log_activity(request, action="sign_document", entity_type="document",
                         entity_id=doc.id, description=f"Signed {doc.title}")
            messages.success(request, f"Signed: {doc.title}")
        return redirect(request.path)

    if action == "submit_stage":
        forms_ok = all(
            (responses.get(f.id) and not responses[f.id].is_draft
             and _required_satisfied(f, responses[f.id].answers, responses[f.id].files))
            for f in forms
        )
        docs_ok = all(d.signed_by(user.id) for d in docs if d.is_required)
        if not (forms_ok and docs_ok):
            messages.error(request, "Complete all forms and sign all documents before submitting.")
            return redirect(request.path)
        user.status = pipeline.SUBMIT_STATUS[stage]
        user.save(update_fields=["status"])
        log_activity(request, action=f"submit_{stage}", entity_type="employee",
                     entity_id=user.id, description=f"Submitted {stage} for review")
        messages.success(request, f"{STAGE_TITLES.get(stage, stage)} submitted for review.")
        
        from ..services.email_service import EmailService, _small_portal_link
        from ..models import User
        admins = User.objects.filter(role__in=["super_admin", "admin"], is_active=True)
        if user.tenant_id:
            admins = admins.filter(tenant_id=user.tenant_id)
        
        template_map = {
            "pre_onboarding": "pre_onboarding_submitted",
            "onboarding": "onboarding_docs_submitted"
        }
        tk = template_map.get(stage)
        if tk:
            for admin in admins:
                EmailService.send_email(
                    to_email=admin.email,
                    template_key=tk,
                    context={
                        "employee_name": user.full_name or user.email,
                        "employee_email": user.email,
                        "department": user.department.name if user.department else "their department",
                        "small_portal_link_review": _small_portal_link(request.build_absolute_uri(f"/admin/employees/{user.id}/"))
                    }
                )
        return redirect(request.path)

    # Save a single form (draft or final)
    form_id = request.POST.get("form_id")
    form = next((f for f in forms if str(f.id) == str(form_id)), None)
    if not form:
        messages.error(request, "Unknown form.")
        return redirect(request.path)

    is_draft = action == "save_draft"
    answers, files = _collect_answers(request, form)
    resp = responses.get(form.id) or FormResponse(employee=user, form=form)
    resp.answers = answers
    merged_files = dict(resp.files or {})
    merged_files.update(files)
    resp.files = merged_files
    resp.is_draft = is_draft
    resp.submitted_at = timezone.now()
    resp.save()

    if not is_draft and form.required_field_names() and not _required_satisfied(
        form, answers, merged_files
    ):
        messages.warning(request, f"'{form.name}' saved, but some required fields are still empty.")
    else:
        messages.success(request, f"'{form.name}' saved." if not is_draft
                         else f"Draft saved for '{form.name}'.")
    return redirect(request.path)


def _collect_answers(request, form):
    answers, files = {}, {}
    for field in form.get_all_fields():
        name = field["field_name"]
        key = f"field_{name}"
        ftype = field.get("field_type")
        if ftype == "file":
            upload = request.FILES.get(key)
            if upload:
                files[name] = _save_form_file(request.user, form, name, upload)
                answers[name] = upload.name
        elif ftype == "checkbox":
            answers[name] = request.POST.getlist(key)
        elif ftype == "yesno":
            answers[name] = "yes" if request.POST.get(key) else "no"
        else:
            answers[name] = request.POST.get(key, "")
    return answers, files


def _save_form_file(user, form, field_name, upload):
    folder = os.path.join(settings.MEDIA_ROOT, "form_uploads", str(user.id))
    os.makedirs(folder, exist_ok=True)
    fname = f"{form.id}_{field_name}_{upload.name}"
    with open(os.path.join(folder, fname), "wb") as fh:
        for chunk in upload.chunks():
            fh.write(chunk)
    return f"form_uploads/{user.id}/{fname}"


def _required_satisfied(form, answers, files):
    for name in form.required_field_names():
        if name in (files or {}):
            continue
        if (answers or {}).get(name) in (None, "", [], {}):
            return False
    return True


def _onboarding_locked(user):
    if user.onboarding_unlock_date and user.onboarding_unlock_date > timezone.now().date():
        return True
    return False


@login_required
@require_http_methods(["GET", "POST"])
def pre_onboarding(request):
    return _stage_view(request, "pre_onboarding", "employee/stage.html")


@login_required
@require_http_methods(["GET", "POST"])
def onboarding(request):
    return _stage_view(request, "onboarding", "employee/stage.html")


@login_required
@require_http_methods(["GET", "POST"])
def post_onboarding(request):
    return _stage_view(request, "post_onboarding", "employee/stage.html")


@login_required
@require_http_methods(["GET", "POST"])
def fill_form(request, form_id):
    """Single-form fill (standalone/quiz/survey style forms)."""
    redir = _employee_only(request)
    if redir:
        return redir
    form = get_object_or_404(Form, id=form_id, is_active=True)
    resp = FormResponse.objects.filter(employee=request.user, form=form).first()
    if request.method == "POST":
        answers, files = _collect_answers(request, form)
        resp = resp or FormResponse(employee=request.user, form=form)
        resp.answers = answers
        merged = dict(resp.files or {})
        merged.update(files)
        resp.files = merged
        resp.is_draft = request.POST.get("action") == "save_draft"
        resp.submitted_at = timezone.now()
        resp.save()
        messages.success(request, "Response saved.")
        return redirect("employee_home")
    return render(request, "employee/fill_form.html", {
        "form": form,
        "answers": resp.answers if resp else {},
        "files": resp.files if resp else {},
    })
