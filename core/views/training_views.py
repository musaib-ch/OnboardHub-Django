"""Training & Learning Paths (post-onboarding, increment 1).

Stays within the locked 13-table schema — no new tables:
  • Learning path  = Content(kind="learning_path"); ordered modules + rules in `meta`.
  • Training module = Content(kind="training") (authored/consumed via content_views).
  • Enrollment      = Engagement(kind="enrollment", content=<path>); progress in `data`.
  • Assignment rules= AppSetting JSON ("training_assignment_rules"), via automation.get_rules.
"""
import datetime
import secrets

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from ..automation import get_rules, save_rules
from ..decorators import login_required, permission_required
from ..models import Content, Engagement, Notification, OrgUnit, User
from ..services import log_activity, notify

DUE_SOON_DAYS = 3

ASSIGN_KEY = "training_assignment_rules"
MATCH_FIELDS = ["role", "department_id", "grade", "location_code", "employee_type"]


# ─────────────────────────────────────────────────────────────────────────────
# Path / progress helpers
# ─────────────────────────────────────────────────────────────────────────────
def _ordered_modules(path):
    """Return [(Content module, required_bool)] in the path's configured order."""
    entries = (path.meta or {}).get("modules", [])
    by_id = {c.id: c for c in Content.objects.filter(
        id__in=[e.get("content_id") for e in entries], kind="training"
    )}
    out = []
    for e in entries:
        mod = by_id.get(e.get("content_id"))
        if mod:
            out.append((mod, bool(e.get("required", True))))
    return out


def _completed_ids(user, module_ids):
    if not module_ids:
        return set()
    return set(Engagement.objects.filter(
        user=user, kind="enrollment", content_id__in=module_ids, status="completed",
    ).values_list("content_id", flat=True))


def _scoped_employees_qs(viewer, qs):
    from ..permissions import role_scope_type
    scope_type = role_scope_type(viewer.role)
    if scope_type == "department":
        depts = (viewer.scope or {}).get("departments") or []
        return qs.filter(department_id__in=depts) if depts else qs.none()
    if scope_type == "location":
        locs = (viewer.scope or {}).get("locations") or []
        return qs.filter(location_code__in=locs) if locs else qs.none()
    return qs


def recompute_enrollment(enrollment):
    """Recompute progress/status from module completions; stamp cert + recurrence.

    Returns True if the enrollment transitioned to completed on this call.
    """
    path = enrollment.content
    mods = _ordered_modules(path)
    required = [m for m, req in mods if req] or [m for m, _ in mods]
    required_ids = [m.id for m in required]
    done = _completed_ids(enrollment.user, required_ids)
    total = len(required_ids)
    pct = int(round(len(done) / total * 100)) if total else 100

    data = dict(enrollment.data or {})
    was_completed = enrollment.status == "completed"
    enrollment.progress = pct

    just_completed = False
    if total and len(done) >= total:
        if not was_completed:
            enrollment.status = "completed"
            enrollment.completed_at = timezone.now()
            data.setdefault("certificate_no", f"OH-{path.id}-{enrollment.user_id}-{secrets.token_hex(3).upper()}")
            rec_days = int((path.meta or {}).get("recurrence_days") or 0)
            if rec_days > 0:
                data["recurs_at"] = (timezone.now() + datetime.timedelta(days=rec_days)).isoformat()
            just_completed = True
    elif enrollment.status == "assigned" and len(done) > 0:
        enrollment.status = "in_progress"

    enrollment.data = data
    enrollment.save(update_fields=["progress", "status", "completed_at", "data"])
    return just_completed


def _is_overdue(enrollment):
    return bool(
        enrollment.due_date and enrollment.status != "completed"
        and enrollment.due_date < timezone.now().date()
    )


# ─────────────────────────────────────────────────────────────────────────────
# Assignment engine
# ─────────────────────────────────────────────────────────────────────────────
def _employee_matches(emp, match):
    for key in MATCH_FIELDS:
        want = match.get(key)
        if want in (None, "", []):
            continue
        if key == "department_id":
            if str(getattr(emp, "department_id", None)) != str(want):
                return False
        elif str(getattr(emp, key, None)) != str(want):
            return False
    return True


def _matching_employees(match, tenant=None):
    qs = User.objects.filter(role=match.get("role") or "employee", is_active=True)
    qs = qs.exclude(status__in=["deleted", "archived"])
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    if match.get("department_id"):
        qs = qs.filter(department_id=match["department_id"])
    for key in ("grade", "location_code", "employee_type"):
        if match.get(key):
            qs = qs.filter(**{key: match[key]})
    return qs


def assign_path_to_user(user, path, due_days=None, actor=None, rule_id=None):
    """Create an enrollment if the user isn't already enrolled in this path.

    Returns the Engagement (new or existing).
    """
    existing = Engagement.objects.filter(
        user=user, kind="enrollment", content=path,
    ).first()
    if existing:
        return existing
    due_date = None
    if due_days:
        due_date = timezone.now().date() + datetime.timedelta(days=int(due_days))
    eng = Engagement.objects.create(
        kind="enrollment", user=user, content=path, tenant=user.tenant,
        title=path.title, status="assigned", progress=0, due_date=due_date,
        data={
            "assigned_by": getattr(actor, "id", None),
            "assigned_at": timezone.now().isoformat(),
            "rule_id": rule_id,
        },
    )
    notify(user, "New training assigned",
           f"“{path.title}” has been assigned to you"
           + (f". Due {due_date:%d %b %Y}." if due_date else "."),
           link="/learn/my-learning/", category="info")
    return eng


def apply_assignment_rules(user=None, actor=None):
    """Apply active assignment rules. Scoped to one user, or all matches if None.

    Returns the number of new enrollments created.
    """
    created = 0
    for rule in get_rules(ASSIGN_KEY):
        if not rule.get("active", True):
            continue
        path = Content.objects.filter(
            id=rule.get("path_content_id"), kind="learning_path", is_active=True,
        ).first()
        if not path:
            continue
        match = rule.get("match", {})
        targets = [user] if user is not None else _matching_employees(match, path.tenant)
        for emp in targets:
            if user is not None and not _employee_matches(emp, match):
                continue
            before = Engagement.objects.filter(
                user=emp, kind="enrollment", content=path,
            ).exists()
            assign_path_to_user(emp, path, due_days=rule.get("due_days"),
                                actor=actor, rule_id=rule.get("id"))
            if not before:
                created += 1
    return created


# ─────────────────────────────────────────────────────────────────────────────
# Admin views
# ─────────────────────────────────────────────────────────────────────────────
@permission_required("manage_training")
@require_http_methods(["GET", "POST"])
def learning_paths(request):
    hrbp_depts = (request.user.scope or {}).get("departments") or [] if request.user.role == "hrbp" else []
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            path = Content.objects.create(
                kind="learning_path", tenant=request.user.tenant,
                created_by=request.user,
                title=(request.POST.get("title") or "Untitled path").strip(),
                category=(request.POST.get("category") or "").strip(),
                body=(request.POST.get("description") or "").strip(),
                meta={"modules": [], "due_days": 30, "recurrence_days": 0},
                target_departments=hrbp_depts,
            )
            messages.success(request, "Learning path created — add modules next.")
            return redirect("admin_learning_path_edit", pk=path.id)
        if action == "delete":
            p = Content.objects.filter(id=request.POST.get("path_id"), kind="learning_path").first()
            if p:
                if request.user.role == "hrbp" and p.target_departments:
                    if not any(int(tid) in hrbp_depts for tid in p.target_departments if str(tid).isdigit() or isinstance(tid, int)):
                        messages.error(request, "This path is outside your scope.")
                        return redirect("admin_learning_paths")
                p.delete()
                messages.success(request, "Learning path deleted.")
        elif action == "toggle":
            p = Content.objects.filter(id=request.POST.get("path_id"), kind="learning_path").first()
            if p:
                if request.user.role == "hrbp" and p.target_departments:
                    if not any(int(tid) in hrbp_depts for tid in p.target_departments if str(tid).isdigit() or isinstance(tid, int)):
                        messages.error(request, "This path is outside your scope.")
                        return redirect("admin_learning_paths")
                p.is_active = not p.is_active
                p.save(update_fields=["is_active"])
        return redirect("admin_learning_paths")

    paths_qs = Content.objects.filter(kind="learning_path").order_by("display_order", "-created_at")
    paths = []
    depts_map = {d.id: d.name for d in OrgUnit.objects.filter(kind="department", is_active=True)}
    for p in paths_qs:
        target_ids = p.target_departments or []
        if request.user.role == "hrbp":
            if target_ids and not any(int(tid) in hrbp_depts for tid in target_ids if str(tid).isdigit() or isinstance(tid, int)):
                continue
        p.target_dept_names = ", ".join([depts_map.get(int(tid), str(tid)) for tid in target_ids if str(tid).isdigit() or isinstance(tid, int)]) or "Global / All"
        paths.append(p)
    counts = {}
    for p in paths:
        counts[p.id] = {
            "modules": len((p.meta or {}).get("modules", [])),
            "enrolled": Engagement.objects.filter(kind="enrollment", content=p).count(),
            "completed": Engagement.objects.filter(kind="enrollment", content=p, status="completed").count(),
        }
    return render(request, "admin/learning_paths.html", {"paths": paths, "counts": counts})


@permission_required("manage_training")
@require_http_methods(["GET", "POST"])
def learning_path_edit(request, pk):
    path = get_object_or_404(Content, id=pk, kind="learning_path")
    hrbp_depts = (request.user.scope or {}).get("departments") or [] if request.user.role == "hrbp" else []
    if request.user.role == "hrbp" and path.target_departments:
        if not any(int(tid) in hrbp_depts for tid in path.target_departments if str(tid).isdigit() or isinstance(tid, int)):
            messages.error(request, "This learning path is outside your scope.")
            return redirect("admin_learning_paths")
    if request.method == "POST":
        path.title = (request.POST.get("title") or path.title).strip()
        path.category = (request.POST.get("category") or "").strip()
        path.body = (request.POST.get("description") or "").strip()
        meta = dict(path.meta or {})
        # Included modules (module_ids checkboxes), ordered by their order_<id>
        # number input, with required_<id> checkboxes marking required.
        ids = [int(x) for x in request.POST.getlist("module_ids") if x.isdigit()]

        def _order_of(i):
            try:
                return int(request.POST.get(f"order_{i}") or 0)
            except (ValueError, TypeError):
                return 0

        ids.sort(key=_order_of)
        required = set(request.POST.getlist("required_ids"))
        meta["modules"] = [{"content_id": i, "required": str(i) in required} for i in ids]
        try:
            meta["due_days"] = max(0, int(request.POST.get("due_days") or 0))
        except ValueError:
            meta["due_days"] = 30
        try:
            meta["recurrence_days"] = max(0, int(request.POST.get("recurrence_days") or 0))
        except ValueError:
            meta["recurrence_days"] = 0
        path.meta = meta
        
        # Target departments
        t_depts = []
        for val in request.POST.getlist("target_departments"):
            val = val.strip()
            if val.isdigit():
                t_depts.append(int(val))
        if request.user.role == "hrbp":
            t_depts = [tid for tid in t_depts if int(tid) in hrbp_depts]
            if not t_depts:
                t_depts = hrbp_depts
        path.target_departments = t_depts
        
        path.save()
        log_activity(request, action="edit_learning_path", entity_type="learning_path",
                     entity_id=path.id, description=f"Edited path {path.title}")
        messages.success(request, "Learning path saved.")
        return redirect("admin_learning_path_edit", pk=path.id)

    chosen = (path.meta or {}).get("modules", [])
    chosen_ids = [e.get("content_id") for e in chosen]
    chosen_required = {e.get("content_id") for e in chosen if e.get("required", True)}
    modules_by_id = {c.id: c for c in Content.objects.filter(kind="training")}
    ordered_chosen = [modules_by_id[i] for i in chosen_ids if i in modules_by_id]
    available_qs = Content.objects.filter(kind="training", is_active=True).order_by("title")
    available = []
    for c in available_qs:
        if c.id in chosen_ids:
            continue
        if request.user.role == "hrbp":
            t_depts = c.target_departments or []
            if t_depts and not any(int(tid) in hrbp_depts for tid in t_depts if str(tid).isdigit() or isinstance(tid, int)):
                continue
        available.append(c)
    from ..models import OrgUnit
    depts = OrgUnit.objects.filter(kind="department", is_active=True)
    if request.user.role == "hrbp":
        depts = depts.filter(id__in=hrbp_depts)
    t_depts_list = [int(tid) for tid in path.target_departments or [] if str(tid).isdigit() or isinstance(tid, int)]

    return render(request, "admin/learning_path_edit.html", {
        "path": path, "meta": path.meta or {},
        "chosen": ordered_chosen, "chosen_required": chosen_required,
        "available": available,
        "departments": depts,
        "target_departments_list": t_depts_list,
    })


@permission_required("manage_training")
@require_http_methods(["GET", "POST"])
def learning_path_analytics_view(request, pk):
    """Real-Time Completion Matrix & Employee Transcript Tracking Dashboard for Learning Paths."""
    from ..models import Content, Engagement, User
    from ..services import notify, log_activity

    path = get_object_or_404(Content, id=pk, kind="learning_path")
    modules = (path.meta or {}).get("modules", [])
    total_modules_count = len(modules)
    module_ids = [m.get("content_id") for m in modules if m.get("content_id")]
    module_objects = {c.id: c for c in Content.objects.filter(id__in=module_ids)}

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "nudge":
            user_id = request.POST.get("user_id")
            emp = User.objects.filter(id=user_id).first()
            if emp:
                notify(
                    emp,
                    f"Reminder: Complete {path.title}",
                    f"Please complete your assigned learning path '{path.title}'.",
                    link="/employee/content/training/",
                    category="warning"
                )
                messages.success(request, f"Sent reminder nudge to {emp.full_name}.")
            return redirect("admin_learning_path_analytics", pk=path.id)

    # Enrollments
    enrollments = Engagement.objects.filter(kind="enrollment", content=path).select_related("user").order_by("-created_at")

    tracking_matrix = []
    completed_total = 0
    in_progress_total = 0
    overdue_total = 0

    now_date = timezone.now().date()

    for eng in enrollments:
        emp = eng.user
        eng_data = eng.data or {}
        completed_mod_ids = set(eng_data.get("completed_sections") or [])
        
        done_count = sum(1 for m_id in module_ids if m_id in completed_mod_ids)
        progress_pct = round((done_count / total_modules_count * 100)) if total_modules_count > 0 else (100 if eng.status == "completed" else 0)

        is_overdue = False
        if eng.due_date and eng.due_date < now_date and eng.status != "completed":
            is_overdue = True
            overdue_total += 1

        if eng.status == "completed" or progress_pct >= 100:
            completed_total += 1
            calc_status = "completed"
        else:
            in_progress_total += 1
            calc_status = "overdue" if is_overdue else "in_progress"

        completed_details = [
            {
                "id": m_id,
                "title": module_objects[m_id].title if m_id in module_objects else f"Module #{m_id}",
                "completed": m_id in completed_mod_ids
            }
            for m_id in module_ids
        ]

        tracking_matrix.append({
            "engagement_id": eng.id,
            "employee": emp,
            "status": calc_status,
            "is_overdue": is_overdue,
            "progress": progress_pct,
            "done_count": done_count,
            "total_count": total_modules_count,
            "due_date": eng.due_date,
            "completed_at": eng.completed_at,
            "modules": completed_details
        })

    return render(request, "admin/learning_path_analytics.html", {
        "path": path,
        "total_enrolled": len(enrollments),
        "completed_total": completed_total,
        "in_progress_total": in_progress_total,
        "overdue_total": overdue_total,
        "tracking_matrix": tracking_matrix,
    })


@permission_required("assign_training")
@require_http_methods(["GET", "POST"])
def training_assignments(request):
    hrbp_depts = (request.user.scope or {}).get("departments") or [] if request.user.role == "hrbp" else []
    if request.method == "POST":
        action = request.POST.get("action")
        rules = get_rules(ASSIGN_KEY)
        if action == "add_rule":
            match = {}
            for key in MATCH_FIELDS:
                val = (request.POST.get(key) or "").strip()
                if val:
                    match[key] = val
            if request.user.role == "hrbp":
                dept_id = match.get("department_id")
                if not dept_id or int(dept_id) not in hrbp_depts:
                    match["department_id"] = str(hrbp_depts[0]) if hrbp_depts else ""
            match.setdefault("role", "employee")
            rules.append({
                "id": secrets.token_hex(6),
                "name": (request.POST.get("name") or "Assignment rule").strip(),
                "path_content_id": int(request.POST.get("path_content_id") or 0),
                "match": match,
                "due_days": int(request.POST.get("due_days") or 0),
                "active": True,
            })
            save_rules(ASSIGN_KEY, rules, user=request.user)
            messages.success(request, "Assignment rule added.")
        elif action == "delete_rule":
            rule_id = request.POST.get("rule_id")
            rule = next((r for r in rules if r.get("id") == rule_id), None)
            if rule and request.user.role == "hrbp":
                dept_id = rule.get("match", {}).get("department_id")
                if not dept_id or int(dept_id) not in hrbp_depts:
                    messages.error(request, "This rule is outside your department scope.")
                    return redirect("admin_training_assignments")
            rules = [r for r in rules if r.get("id") != rule_id]
            save_rules(ASSIGN_KEY, rules, user=request.user)
            messages.success(request, "Assignment rule removed.")
        elif action == "run_now":
            n = apply_assignment_rules(actor=request.user)
            messages.success(request, f"Rules applied — {n} new enrollment(s) created.")
        elif action == "manual_assign":
            path = Content.objects.filter(id=request.POST.get("path_content_id"),
                                           kind="learning_path").first()
            emp = User.objects.filter(id=request.POST.get("employee_id"), role="employee").first()
            if path and emp:
                if request.user.role == "hrbp":
                    if path.target_departments and not any(int(tid) in hrbp_depts for tid in path.target_departments if str(tid).isdigit() or isinstance(tid, int)):
                        messages.error(request, "This path is outside your department scope.")
                        return redirect("admin_training_assignments")
                    if emp.department_id not in hrbp_depts:
                        messages.error(request, "This employee is outside your department scope.")
                        return redirect("admin_training_assignments")
                assign_path_to_user(emp, path, due_days=request.POST.get("due_days") or None,
                                    actor=request.user)
                log_activity(request, action="assign_training", entity_type="learning_path",
                             entity_id=path.id, description=f"Assigned {path.title} to {emp.full_name}")
                messages.success(request, f"Assigned “{path.title}” to {emp.full_name}.")
            else:
                messages.error(request, "Pick both a path and an employee.")
        return redirect("admin_training_assignments")

    rules_raw = get_rules(ASSIGN_KEY)
    rules = []
    for r in rules_raw:
        if request.user.role == "hrbp":
            dept_id = r.get("match", {}).get("department_id")
            if not dept_id or int(dept_id) not in hrbp_depts:
                continue
        rules.append(r)

    paths_qs = Content.objects.filter(kind="learning_path", is_active=True).order_by("title")
    paths = []
    for p in paths_qs:
        if request.user.role == "hrbp":
            if p.target_departments and not any(int(tid) in hrbp_depts for tid in p.target_departments if str(tid).isdigit() or isinstance(tid, int)):
                continue
        paths.append(p)

    path_titles = {p.id: p.title for p in Content.objects.filter(kind="learning_path")}
    depts = OrgUnit.objects.filter(kind="department", is_active=True)
    if request.user.role == "hrbp":
        depts = depts.filter(id__in=hrbp_depts)
    employees = User.objects.filter(role="employee").exclude(status="deleted").order_by("full_name")
    employees = _scoped_employees_qs(request.user, employees)

    return render(request, "admin/training_assignments.html", {
        "rules": rules, "paths": paths, "path_titles": path_titles,
        "departments": depts,
        "employees": employees,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Employee views
# ─────────────────────────────────────────────────────────────────────────────
def _path_card(user, path, enrollment=None):
    mods = _ordered_modules(path)
    total = len(mods)
    done = _completed_ids(user, [m.id for m, _ in mods])
    return {
        "path": path,
        "enrollment": enrollment,
        "total": total,
        "done": len(done),
        "pct": enrollment.progress if enrollment else (int(round(len(done) / total * 100)) if total else 0),
        "overdue": _is_overdue(enrollment) if enrollment else False,
    }


@login_required
def my_learning(request):
    user = request.user
    enrollments = (Engagement.objects.filter(user=user, kind="enrollment",
                                              content__kind="learning_path")
                   .select_related("content"))
    if not enrollments.exists():
        messages.warning(request, "No learning paths have been assigned to you yet.")
        return redirect("employee_home")
    assigned, completed = [], []
    enrolled_ids = set()
    for e in enrollments:
        recompute_enrollment(e)
        enrolled_ids.add(e.content_id)
        card = _path_card(user, e.content, e)
        (completed if e.status == "completed" else assigned).append(card)

    # Security: only show assigned learning paths. Hide self-serve catalog.
    catalog = []
    return render(request, "employee/my_learning.html", {
        "assigned": assigned, "completed": completed, "catalog": catalog,
    })


@login_required
@require_http_methods(["GET", "POST"])
def learning_path_detail(request, pk):
    path = get_object_or_404(Content, id=pk, kind="learning_path", is_active=True)
    user = request.user
    enrollment = Engagement.objects.filter(user=user, kind="enrollment", content=path).first()

    if user.role == "employee" and not enrollment:
        messages.error(request, "This learning path has not been assigned to you.")
        return redirect("my_learning")

    if request.method == "POST" and request.POST.get("action") == "enroll":
        if user.role == "employee":
            messages.error(request, "Self-enrollment is disabled. Learning paths must be assigned.")
            return redirect("my_learning")
        enrollment = assign_path_to_user(user, path, due_days=(path.meta or {}).get("due_days"),
                                         actor=user)
        messages.success(request, f"You’re enrolled in “{path.title}”.")
        return redirect("learning_path_detail", pk=path.id)

    if enrollment:
        recompute_enrollment(enrollment)

    mods = _ordered_modules(path)
    done = _completed_ids(user, [m.id for m, _ in mods])
    # Sequential unlock: a module is locked until all earlier ones are complete.
    rows, prior_done = [], True
    for mod, required in mods:
        is_done = mod.id in done
        rows.append({"module": mod, "required": required, "done": is_done, "locked": not prior_done})
        if not is_done:
            prior_done = False
    total = len(mods)
    return render(request, "employee/learning_path_detail.html", {
        "path": path, "enrollment": enrollment, "rows": rows,
        "total": total, "done": len(done),
        "pct": enrollment.progress if enrollment else 0,
        "completed": bool(enrollment and enrollment.status == "completed"),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Scheduled: due-soon / overdue nudges, escalation, recurrence reset
#   Run daily via `python manage.py training_reminders` (cron / Task Scheduler).
# ─────────────────────────────────────────────────────────────────────────────
def _recent_dupe(user, title, hours=20):
    return Notification.objects.filter(
        user=user, title=title,
        created_at__gte=timezone.now() - datetime.timedelta(hours=hours),
    ).exists()


def run_training_reminders():
    today = timezone.now().date()
    soon = today + datetime.timedelta(days=DUE_SOON_DAYS)
    counts = {"due_soon": 0, "overdue": 0, "escalated": 0, "recurred": 0}

    active = (Engagement.objects.filter(kind="enrollment", content__kind="learning_path")
              .exclude(status="completed").select_related("content", "user"))
    for e in active:
        if not e.due_date:
            continue
        path = e.content
        if e.due_date < today:
            title = f"Overdue training: {path.title}"
            if not _recent_dupe(e.user, title):
                notify(e.user, title,
                       f"“{path.title}” was due {e.due_date:%d %b %Y}. Please complete it.",
                       link="/learn/my-learning/", category="warning")
                counts["overdue"] += 1
            # Escalate to admins of the same tenant.
            admins = User.objects.filter(role__in=["super_admin", "admin"], is_active=True)
            if e.user.tenant_id:
                admins = admins.filter(tenant_id=e.user.tenant_id)
            for admin in admins:
                atitle = f"Overdue training — {e.user.full_name}"
                if not _recent_dupe(admin, atitle):
                    notify(admin, atitle,
                           f"{e.user.full_name} is overdue on “{path.title}” (due {e.due_date:%d %b %Y}).",
                           link=f"/admin/employees/{e.user_id}/", category="warning")
                    counts["escalated"] += 1
        elif e.due_date <= soon:
            title = f"Training due soon: {path.title}"
            if not _recent_dupe(e.user, title):
                notify(e.user, title,
                       f"“{path.title}” is due {e.due_date:%d %b %Y}.",
                       link="/learn/my-learning/", category="info")
                counts["due_soon"] += 1

    # Recurrence: completed enrollments past their recurs_at reset for recertification.
    now = timezone.now()
    completed = (Engagement.objects.filter(kind="enrollment", content__kind="learning_path",
                                           status="completed")
                 .select_related("content", "user"))
    for e in completed:
        recurs_at = (e.data or {}).get("recurs_at")
        if not recurs_at:
            continue
        try:
            due = datetime.datetime.fromisoformat(recurs_at)
        except (ValueError, TypeError):
            continue
        if due > now:
            continue
        path = e.content
        module_ids = [m.id for m, _ in _ordered_modules(path)]
        # Clear prior module completions so the path must be re-done.
        Engagement.objects.filter(user=e.user, kind="enrollment",
                                  content_id__in=module_ids, status="completed").delete()
        rec_days = int((path.meta or {}).get("recurrence_days") or 0)
        e.status = "assigned"
        e.progress = 0
        e.completed_at = None
        e.due_date = (now.date() + datetime.timedelta(days=rec_days)) if rec_days else None
        data = dict(e.data or {})
        data.pop("recurs_at", None)
        data.pop("certificate_no", None)
        e.data = data
        e.save(update_fields=["status", "progress", "completed_at", "due_date", "data"])
        notify(e.user, f"Recertification due: {path.title}",
               f"It’s time to renew “{path.title}”.",
               link="/learn/my-learning/", category="info")
        counts["recurred"] += 1

    return counts


@login_required
def learning_certificate(request, pk):
    path = get_object_or_404(Content, id=pk, kind="learning_path")
    enrollment = get_object_or_404(
        Engagement, user=request.user, kind="enrollment", content=path, status="completed",
    )
    return render(request, "employee/certificate.html", {
        "path": path, "enrollment": enrollment, "user": request.user,
        "cert_no": (enrollment.data or {}).get("certificate_no", f"OH-{path.id}-{request.user.id}"),
    })
