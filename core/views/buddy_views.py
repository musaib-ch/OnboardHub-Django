"""Onboarding Buddy & Mentorship Program Views.

Handles admin pairing studio, employee buddy dashboard, mentor mentee tracking,
and 1-on-1 check-in meeting logs. Uses Engagement(kind='mentorship').
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta

from ..models import Engagement, User, OrgUnit
from ..services import log_activity, notify
from ..decorators import roles_required


@roles_required("super_admin", "admin", "hrbp")
@require_http_methods(["GET", "POST"])
def admin_buddy_program(request):
    """Admin Buddy Program Studio: Manage buddy pairings and check-in metrics scoped by department."""
    from .admin_views import scoped_employee_qs
    tenant = request.user.tenant

    # Department scoped base user query
    scoped_users_qs = scoped_employee_qs(request.user, User.objects.filter(is_active=True))

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "pair":
            new_hire_id = request.POST.get("new_hire_id")
            buddy_id = request.POST.get("buddy_id")
            notes = (request.POST.get("notes") or "").strip()

            new_hire = scoped_users_qs.filter(id=new_hire_id).first()
            buddy = scoped_users_qs.filter(id=buddy_id).first()

            if not new_hire:
                messages.error(request, "You can only assign Onboarding Buddies to employees in your department.")
                return redirect("admin_buddy_program")

            if new_hire and buddy:
                # Create or update mentorship engagement
                eng, created = Engagement.objects.get_or_create(
                    kind="mentorship",
                    user=new_hire,
                    defaults={
                        "counterparty": buddy,
                        "tenant": tenant,
                        "title": f"Onboarding Buddy: {buddy.full_name}",
                        "description": notes,
                        "status": "active",
                        "data": {
                            "paired_at": timezone.now().strftime("%Y-%m-%d"),
                            "sessions": [
                                {"title": "Day 1 Welcome Coffee & Intro", "status": "pending", "target_day": 1},
                                {"title": "Week 1 Systems & Workplace Sync", "status": "pending", "target_day": 7},
                                {"title": "Month 1 Progress & Feedback Check-In", "status": "pending", "target_day": 30},
                            ]
                        }
                    }
                )
                if not created:
                    eng.counterparty = buddy
                    eng.description = notes
                    eng.status = "active"
                    eng.save()

                # Notify both
                notify(new_hire, f"Onboarding Buddy Assigned: {buddy.full_name}",
                       f"{buddy.full_name} has been assigned as your Onboarding Buddy! Check your Buddy Dashboard to connect.",
                       link="/employee/buddy/", category="info")
                notify(buddy, f"Assigned as Onboarding Buddy for {new_hire.full_name}",
                       f"You have been paired as the Onboarding Buddy for {new_hire.full_name}.",
                       link="/employee/buddy/", category="info")

                log_activity(request, action="pair_buddy", entity_type="mentorship", entity_id=eng.id,
                             description=f"Paired new hire {new_hire.full_name} with buddy {buddy.full_name}")
                messages.success(request, f"Successfully paired {new_hire.full_name} with Onboarding Buddy {buddy.full_name}.")

        elif action == "unpair":
            eng_id = request.POST.get("engagement_id")
            eng = Engagement.objects.filter(id=eng_id, kind="mentorship").first()
            if eng and scoped_users_qs.filter(id=eng.user_id).exists():
                eng.delete()
                messages.success(request, "Buddy pairing removed.")
            else:
                messages.error(request, "You can only manage pairings for employees in your department.")

        return redirect("admin_buddy_program")

    # Get active mentorship pairings scoped to viewer's allowed employees
    scoped_user_ids = scoped_users_qs.values_list("id", flat=True)
    pairings = Engagement.objects.filter(kind="mentorship", status="active", user_id__in=scoped_user_ids).select_related("user", "counterparty", "user__department")

    paired_user_ids = set(pairings.values_list("user_id", flat=True))

    # Employees eligible to be paired (new hires in viewer's scope)
    unassigned_new_hires = scoped_users_qs.exclude(id__in=paired_user_ids).order_by("-date_of_joining", "full_name")

    # Employees eligible to be buddies (experienced staff in viewer's scope)
    potential_buddies = scoped_users_qs.order_by("full_name")

    # Statistics
    total_pairings = len(pairings)
    unassigned_count = unassigned_new_hires.count()
    
    # Calculate completed check-ins across pairings
    total_sessions = 0
    completed_sessions = 0
    for p in pairings:
        sess_list = (p.data or {}).get("sessions", [])
        total_sessions += len(sess_list)
        completed_sessions += sum(1 for s in sess_list if s.get("status") == "completed")

    checkin_completion_rate = round((completed_sessions / total_sessions * 100), 1) if total_sessions > 0 else 0

    return render(request, "admin/buddy_program.html", {
        "pairings": pairings,
        "unassigned_new_hires": unassigned_new_hires,
        "potential_buddies": potential_buddies,
        "total_pairings": total_pairings,
        "unassigned_count": unassigned_count,
        "checkin_completion_rate": checkin_completion_rate,
    })


def check_buddy_eligibility(user):
    """Buddy program is enabled ONLY once:
    1. Employee's date_of_joining has passed (date_of_joining <= today).
    2. Offer status is Accepted.
    3. Medical is approved.
    4. Pre-onboarding is approved.
    """
    if user.role in ('super_admin', 'admin', 'hrbp', 'medical_approver', 'offer_sender'):
        return True, []  # Staff roles always have access to buddy management

    today = timezone.now().date()
    reasons = []
    
    # 1. Date of joining check
    doj_passed = bool(user.date_of_joining and user.date_of_joining <= today)
    reasons.append({"label": "Date of Joining Passed", "met": doj_passed, "detail": f"Joining Date: {user.date_of_joining or 'Not set'}"})

    # 2. Offer Acceptance check
    from ..models_offers import Offer
    offer_accepted = Offer.objects.filter(candidate_user=user, status="accepted").exists()
    reasons.append({"label": "Offer Letter Accepted", "met": offer_accepted, "detail": "Offer accepted by employee" if offer_accepted else "Pending offer signature"})

    # 3. Medical Clearance check
    medical_approved = user.status in ("pre_onboarding", "onboarding", "post_onboarding", "completed")
    reasons.append({"label": "Medical Clearance Approved", "met": medical_approved, "detail": "Medical cleared" if medical_approved else "Pending medical clearance"})

    # 4. Pre-Onboarding Forms check
    pre_onboarding_approved = user.status in ("onboarding", "post_onboarding", "completed")
    reasons.append({"label": "Pre-Onboarding Approved", "met": pre_onboarding_approved, "detail": "Pre-onboarding approved" if pre_onboarding_approved else "Pending pre-onboarding review"})

    is_eligible = all(r["met"] for r in reasons)
    return is_eligible, reasons


@login_required
def employee_buddy_dashboard(request):
    """Employee & Mentor Buddy Portal. View assigned buddy, schedule 1-on-1s, log check-in notes."""
    user = request.user

    # Check eligibility rules for employee
    is_eligible, eligibility_reasons = check_buddy_eligibility(user)

    # 1. Check if current user is a New Hire with an assigned Buddy
    my_buddy_engagement = Engagement.objects.filter(kind="mentorship", user=user, status="active").select_related("counterparty", "counterparty__department").first()
    my_buddy = my_buddy_engagement.counterparty if my_buddy_engagement else None

    # 2. Check if current user is acting as a Mentor/Buddy for others
    as_mentor_engagements = Engagement.objects.filter(kind="mentorship", counterparty=user, status="active").select_related("user", "user__department")

    return render(request, "employee/buddy_dashboard.html", {
        "my_buddy_engagement": my_buddy_engagement,
        "my_buddy": my_buddy,
        "as_mentor_engagements": as_mentor_engagements,
        "is_eligible": is_eligible,
        "eligibility_reasons": eligibility_reasons,
    })


@login_required
@require_http_methods(["POST"])
def propose_buddy_plan(request):
    """Post or update an onboarding mentorship plan (Mentor or Admin action only)."""
    eng_id = request.POST.get("engagement_id")
    plan_title = (request.POST.get("plan_title") or "Mentorship & Onboarding Plan").strip()
    milestones_raw = request.POST.getlist("milestone_titles")

    eng = get_object_or_404(Engagement, id=eng_id, kind="mentorship")
    
    # Permission check: Only Mentor or Admin can set/update the plan structure
    if request.user.id != eng.counterparty_id and request.user.role not in ('super_admin', 'admin'):
        messages.error(request, "Only your assigned Onboarding Buddy (Mentor) or HR Admin can post or edit the overall plan. You can sign off and add notes to individual milestones below.")
        return redirect("employee_buddy_dashboard")

    data = dict(eng.data or {})
    sessions = []
    
    # Build milestones list
    for idx, m_title in enumerate(milestones_raw):
        m_title = m_title.strip()
        if m_title:
            sessions.append({
                "id": f"m_{idx + 1}",
                "title": m_title,
                "status": "pending",
                "signed_off_by": [],
                "target_day": (idx + 1) * 7,
                "notes": ""
            })

    if not sessions:
        # Default milestones if none supplied
        sessions = [
            {"id": "m_1", "title": "Day 1 Welcome Coffee & Codebase Walkthrough", "status": "pending", "signed_off_by": [], "target_day": 1, "notes": ""},
            {"id": "m_2", "title": "Week 1 Systems & Tooling Setup Sync", "status": "pending", "signed_off_by": [], "target_day": 7, "notes": ""},
            {"id": "m_3", "title": "Month 1 Progress Review & Feedback", "status": "pending", "signed_off_by": [], "target_day": 30, "notes": ""},
        ]

    data["plan_title"] = plan_title
    data["plan_status"] = "active"
    data["posted_by_id"] = request.user.id
    data["posted_by_name"] = request.user.full_name
    data["posted_at"] = timezone.now().strftime("%Y-%m-%d %H:%M")
    data["sessions"] = sessions

    eng.data = data
    eng.save()

    # Notify mentee
    notify(eng.user, f"Mentorship Plan Posted by {request.user.full_name}",
           f"Your Onboarding Buddy {request.user.full_name} posted the Onboarding Plan '{plan_title}'. Review your milestones and sign off as you complete them.",
           link="/employee/buddy/", category="info")

    log_activity(request, action="post_buddy_plan", entity_type="mentorship", entity_id=eng.id,
                 description=f"{request.user.full_name} posted mentorship plan '{plan_title}' for {eng.user.full_name}")
    messages.success(request, f"Successfully posted onboarding plan '{plan_title}' for {eng.user.full_name}.")
    return redirect("employee_buddy_dashboard")


@login_required
@require_http_methods(["POST"])
def signoff_buddy_milestone(request):
    """Sign off on a milestone check-in (requires dual sign-off from both mentor & mentee)."""
    eng_id = request.POST.get("engagement_id")
    session_title = request.POST.get("session_title", "").strip()
    notes = request.POST.get("notes", "").strip()

    eng = get_object_or_404(Engagement, id=eng_id, kind="mentorship")
    if request.user.id not in (eng.user_id, eng.counterparty_id) and request.user.role not in ('super_admin', 'admin'):
        messages.error(request, "You are not authorized to sign off on this milestone.")
        return redirect("employee_buddy_dashboard")

    data = dict(eng.data or {})
    sessions = data.get("sessions", [])
    required_ids = {eng.user_id, eng.counterparty_id}

    milestone_found = False
    for s in sessions:
        if s.get("title") == session_title:
            milestone_found = True
            signed_off = set(s.get("signed_off_by") or [])
            signed_off.add(request.user.id)
            s["signed_off_by"] = list(signed_off)

            if notes:
                s["notes"] = f"{s.get('notes', '')}\n[{request.user.full_name}]: {notes}".strip()

            # Dual sign-off check: if both mentor and mentee (or admin) signed off -> complete!
            if required_ids.issubset(signed_off) or request.user.role in ('super_admin', 'admin'):
                s["status"] = "completed"
                s["completed_at"] = timezone.now().strftime("%Y-%m-%d %H:%M")
                s["completed_by"] = "Dual Agreement"
                messages.success(request, f"Milestone '{session_title}' fully agreed and completed by both parties!")
            else:
                s["status"] = "pending_counterparty"
                counterparty = eng.counterparty if request.user.id == eng.user_id else eng.user
                notify(counterparty, f"Milestone Sign-Off Request: {session_title}",
                       f"{request.user.full_name} signed off on '{session_title}'. Please review and agree to complete.",
                       link="/employee/buddy/", category="info")
                messages.info(request, f"You signed off on '{session_title}'. Awaiting counterparty agreement.")
            break

    if not milestone_found and session_title:
        # Add new milestone signed off by current user
        is_admin = request.user.role in ('super_admin', 'admin')
        status_val = "completed" if is_admin else "pending_counterparty"
        sessions.append({
            "id": f"m_{len(sessions) + 1}",
            "title": session_title,
            "status": status_val,
            "signed_off_by": [request.user.id],
            "notes": f"[{request.user.full_name}]: {notes}".strip() if notes else "",
            "target_day": 1
        })
        messages.info(request, f"Logged milestone '{session_title}'.")

    data["sessions"] = sessions
    eng.data = data
    eng.save()

    return redirect("employee_buddy_dashboard")
