"""
Enterprise onboarding success plan service.

Uses the existing consolidated schema only:
- Content(kind="onboarding_plan") for reusable templates
- Engagement(kind="onboarding_plan") for employee plan instances
- ReviewMessage for activity discussion threads
- Notification for alerts
"""
from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from ..models import Content, Engagement, Form, FormResponse, OnboardingDocument, ReviewMessage, User
from ..permissions import is_staff_role, role_scope_type
from . import log_activity, notify

PLAN_SCHEMA_VERSION = 2
TEMPLATE_KIND = "onboarding_plan"
PLAN_KIND = "onboarding_plan"
THREAD_PREFIX = "onboarding_plan"

DEFAULT_PHASES = [
    {"id": "day-30", "label": "30 Days", "description": "Foundation, orientation, and first wins."},
    {"id": "day-60", "label": "60 Days", "description": "Role confidence, stakeholder alignment, and delivery."},
    {"id": "day-90", "label": "90 Days", "description": "Ownership, performance rhythm, and long-term success."},
]

ACTIVITY_TYPES = [
    "task", "goal", "meeting", "training", "quiz", "course", "document",
    "reading", "survey", "project", "observation", "certification",
    "external_link", "form", "video", "custom",
]

SECTION_LIBRARY = [
    "Company", "HR", "Department", "Systems", "Compliance", "Learning",
    "Meetings", "Projects", "KPIs", "Performance", "Goals", "Documents", "Custom",
]


def _now_iso() -> str:
    return timezone.now().isoformat()


def _date_iso(value) -> Optional[str]:
    if not value:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _uuid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _weight(value: Any) -> int:
    try:
        num = int(value or 0)
    except (TypeError, ValueError):
        num = 0
    return max(1, num or 1)


def _safe_list(value) -> List:
    return value if isinstance(value, list) else []


def _safe_dict(value) -> Dict:
    return value if isinstance(value, dict) else {}


def _normalize_tags(value) -> List[str]:
    if isinstance(value, str):
        parts = [v.strip() for v in value.split(",")]
        return [v for v in parts if v]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _normalize_related(data: Dict[str, Any]) -> Dict[str, Any]:
    data = _safe_dict(data)
    return {
        "content_id": int(data.get("content_id") or 0) or None,
        "course_id": int(data.get("course_id") or 0) or None,
        "form_id": int(data.get("form_id") or 0) or None,
        "session_id": int(data.get("session_id") or 0) or None,
        "document_id": int(data.get("document_id") or 0) or None,
        "url": (data.get("url") or "").strip(),
    }


def _blank_activity(title: str = "", activity_type: str = "task", owner: str = "employee", due_days: int = 0) -> Dict[str, Any]:
    return {
        "id": _uuid("act"),
        "activity_type": activity_type if activity_type in ACTIVITY_TYPES else "task",
        "title": title,
        "description": "",
        "instructions": "",
        "owner": owner,
        "priority": "medium",
        "weight": 1,
        "estimated_time": "",
        "completion_type": "manual",
        "evidence_required": False,
        "allow_attachments": True,
        "related": _normalize_related({}),
        "tags": [],
        "status": "not_started",
        "due_days": max(0, int(due_days or 0)),
        "due_date": None,
        "completed_at": None,
        "approved_at": None,
        "returned_at": None,
        "approved_by_id": None,
        "approved_by_name": "",
        "draft_comment": "",
        "last_comment_at": None,
        "attachments": [],
        "timeline": [],
    }


def _default_template_payload(name: str, department_label: str) -> Dict[str, Any]:
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "title": f"{name} Success Plan",
        "summary": f"Enterprise onboarding roadmap for {name.lower()} roles across {department_label.lower()} workstreams.",
        "audience": {
            "role": "employee",
            "department": department_label,
        },
        "phases": [
            {
                "id": "day-30",
                "label": "30 Days",
                "description": "Build confidence, complete required setup, and learn how the team operates.",
                "sections": [
                    {
                        "id": "company",
                        "label": "Company",
                        "activities": [
                            _blank_activity("Review company mission, values, and operating model", "reading", "employee", 3),
                            _blank_activity("Attend welcome and culture orientation", "meeting", "hr", 5),
                        ],
                    },
                    {
                        "id": "systems",
                        "label": "Systems",
                        "activities": [
                            _blank_activity("Set up required systems and access", "task", "employee", 2),
                            _blank_activity("Complete core systems training", "training", "employee", 7),
                        ],
                    },
                ],
            },
            {
                "id": "day-60",
                "label": "60 Days",
                "description": "Increase ownership, deepen department fluency, and deliver early impact.",
                "sections": [
                    {
                        "id": "department",
                        "label": "Department",
                        "activities": [
                            _blank_activity("Shadow critical department workflows", "observation", "manager", 40),
                            _blank_activity("Lead your first scoped deliverable", "project", "employee", 50),
                        ],
                    },
                    {
                        "id": "meetings",
                        "label": "Meetings",
                        "activities": [
                            _blank_activity("Complete manager check-in and feedback review", "meeting", "manager", 55),
                        ],
                    },
                ],
            },
            {
                "id": "day-90",
                "label": "90 Days",
                "description": "Demonstrate independence, contribution quality, and measurable readiness.",
                "sections": [
                    {
                        "id": "performance",
                        "label": "Performance",
                        "activities": [
                            _blank_activity("Review KPI expectations and first-quarter performance goals", "goal", "manager", 80),
                            _blank_activity("Complete 90-day success review", "meeting", "manager", 90),
                        ],
                    },
                    {
                        "id": "projects",
                        "label": "Projects",
                        "activities": [
                            _blank_activity("Present one improvement idea or completed contribution", "project", "employee", 88),
                        ],
                    },
                ],
            },
        ],
    }


DEFAULT_TEMPLATE_LIBRARY = [
    _default_template_payload("Sales Executive", "Sales"),
    _default_template_payload("Procurement Officer", "Procurement"),
    _default_template_payload("Warehouse Operator", "Operations"),
    _default_template_payload("Finance Executive", "Finance"),
    _default_template_payload("Store Manager", "Retail"),
    _default_template_payload("HR Executive", "Human Resources"),
    _default_template_payload("IT Engineer", "Technology"),
]


def _normalize_activity(activity: Dict[str, Any], employee: Optional[User] = None, start_date=None) -> Dict[str, Any]:
    activity = _safe_dict(activity)
    normalized = {
        "id": activity.get("id") or _uuid("act"),
        "activity_type": (activity.get("activity_type") or "task").strip().lower(),
        "title": (activity.get("title") or "Untitled activity").strip(),
        "description": (activity.get("description") or "").strip(),
        "instructions": (activity.get("instructions") or "").strip(),
        "owner": (activity.get("owner") or "employee").strip().lower(),
        "priority": (activity.get("priority") or "medium").strip().lower(),
        "weight": _weight(activity.get("weight")),
        "estimated_time": (activity.get("estimated_time") or "").strip(),
        "completion_type": (activity.get("completion_type") or "manual").strip().lower(),
        "evidence_required": bool(activity.get("evidence_required")),
        "allow_attachments": bool(activity.get("allow_attachments", True)),
        "related": _normalize_related(activity.get("related") or {}),
        "tags": _normalize_tags(activity.get("tags")),
        "status": (activity.get("status") or "not_started").strip().lower(),
        "due_days": max(0, int(activity.get("due_days") or 0)),
        "due_date": activity.get("due_date"),
        "completed_at": activity.get("completed_at"),
        "approved_at": activity.get("approved_at"),
        "returned_at": activity.get("returned_at"),
        "approved_by_id": activity.get("approved_by_id"),
        "approved_by_name": activity.get("approved_by_name") or "",
        "draft_comment": activity.get("draft_comment") or "",
        "last_comment_at": activity.get("last_comment_at"),
        "attachments": _safe_list(activity.get("attachments")),
        "timeline": _safe_list(activity.get("timeline")),
    }
    if normalized["activity_type"] not in ACTIVITY_TYPES:
        normalized["activity_type"] = "custom"
    if start_date and normalized["due_days"] and not normalized["due_date"]:
        normalized["due_date"] = _date_iso(start_date + timedelta(days=normalized["due_days"]))
    return normalized


def _normalize_section(section: Dict[str, Any], employee: Optional[User] = None, start_date=None) -> Dict[str, Any]:
    section = _safe_dict(section)
    return {
        "id": section.get("id") or _uuid("sec"),
        "label": (section.get("label") or "Custom").strip(),
        "activities": [_normalize_activity(a, employee=employee, start_date=start_date)
                       for a in _safe_list(section.get("activities"))],
    }


def _normalize_phase(phase: Dict[str, Any], employee: Optional[User] = None, start_date=None) -> Dict[str, Any]:
    phase = _safe_dict(phase)
    return {
        "id": phase.get("id") or _uuid("phase"),
        "label": (phase.get("label") or "Phase").strip(),
        "description": (phase.get("description") or "").strip(),
        "sections": [_normalize_section(s, employee=employee, start_date=start_date)
                     for s in _safe_list(phase.get("sections"))],
    }


def _normalize_template_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    phases = _safe_list(payload.get("phases"))
    if not phases:
        phases = [{"id": item["id"], "label": item["label"], "description": item["description"], "sections": []}
                  for item in DEFAULT_PHASES]
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "title": (payload.get("title") or "Onboarding Success Plan").strip(),
        "summary": (payload.get("summary") or "").strip(),
        "audience": _safe_dict(payload.get("audience")),
        "phases": [_normalize_phase(p) for p in phases],
    }


def _build_plan_from_template(template: Dict[str, Any], employee: User, actor: User, title: Optional[str] = None) -> Dict[str, Any]:
    start_date = employee.date_of_joining or timezone.now().date()
    phases = [_normalize_phase(p, employee=employee, start_date=start_date)
              for p in _safe_list(template.get("phases"))]
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "template_title": template.get("title") or "Onboarding Success Plan",
        "plan_title": (title or template.get("title") or "Onboarding Success Plan").strip(),
        "summary": (template.get("summary") or "").strip(),
        "assigned_by_id": actor.id,
        "assigned_by_name": actor.full_name,
        "assigned_at": _now_iso(),
        "employee_id": employee.id,
        "employee_joining_date": _date_iso(employee.date_of_joining),
        "status": "active",
        "phases": phases,
        "timeline": [{
            "event": "assigned",
            "label": "Plan assigned",
            "at": _now_iso(),
            "by_id": actor.id,
            "by_name": actor.full_name,
            "note": f"Assigned {title or template.get('title') or 'plan'}",
        }],
    }


def _thread_key(engagement_id: int, activity_id: str) -> str:
    return f"{THREAD_PREFIX}:{engagement_id}:activity:{activity_id}"


def _serialize_template_content(item: Content) -> Dict[str, Any]:
    payload = _normalize_template_payload(item.meta or {})
    return {
        "id": item.id,
        "title": item.title,
        "category": item.category or "",
        "body": item.body or "",
        "is_active": item.is_active,
        "created_at": item.created_at,
        "meta": payload,
        "phase_count": len(payload.get("phases") or []),
        "activity_count": sum(
            len(section.get("activities") or [])
            for phase in payload.get("phases") or []
            for section in phase.get("sections") or []
        ),
    }


def _activity_completion_status(activity: Dict[str, Any]) -> bool:
    return activity.get("status") in {"completed", "approved", "automatic_complete"}


def _activity_is_overdue(activity: Dict[str, Any]) -> bool:
    due_date = activity.get("due_date")
    if not due_date or _activity_completion_status(activity):
        return False
    try:
        due = datetime.fromisoformat(str(due_date)).date()
    except ValueError:
        return False
    return due < timezone.now().date()


def _check_automatic_completion(employee: User, activity: Dict[str, Any]) -> Optional[str]:
    if activity.get("completion_type") != "automatic":
        return None
    related = _normalize_related(activity.get("related") or {})
    if related.get("content_id"):
        done = Engagement.objects.filter(
            user=employee, kind="enrollment", content_id=related["content_id"], status="completed"
        ).exists()
        if done:
            return "automatic_complete"
    if related.get("course_id"):
        done = Engagement.objects.filter(
            user=employee, kind="enrollment", content_id=related["course_id"], status="completed"
        ).exists()
        if done:
            return "automatic_complete"
    if related.get("form_id"):
        submitted = FormResponse.objects.filter(
            employee=employee, form_id=related["form_id"], is_draft=False
        ).exists()
        if submitted:
            return "automatic_complete"
    if related.get("document_id"):
        doc = OnboardingDocument.objects.filter(id=related["document_id"], is_active=True).first()
        if doc and doc.signed_by(employee.id):
            return "automatic_complete"
    return None


def _scope_employees(viewer: User, qs):
    scope_type = role_scope_type(viewer.role)
    if scope_type == "department":
        depts = (viewer.scope or {}).get("departments") or []
        return qs.filter(department_id__in=depts) if depts else qs.none()
    if scope_type == "location":
        locs = (viewer.scope or {}).get("locations") or []
        return qs.filter(location_code__in=locs) if locs else qs.none()
    return qs


class OnboardingPlanService:
    @classmethod
    def sync_default_templates(cls, actor: Optional[User] = None) -> None:
        for payload in DEFAULT_TEMPLATE_LIBRARY:
            title = payload["title"]
            exists = Content.objects.filter(kind=TEMPLATE_KIND, title=title).exists()
            if not exists:
                Content.objects.create(
                    kind=TEMPLATE_KIND,
                    tenant=getattr(actor, "tenant", None),
                    title=title,
                    category="Onboarding Success Plan",
                    body=payload.get("summary") or "",
                    meta=_normalize_template_payload(payload),
                    is_active=True,
                    created_by=actor,
                )

    @classmethod
    def list_templates(cls, user: User):
        cls.sync_default_templates(actor=user)
        return Content.objects.filter(kind=TEMPLATE_KIND).order_by("is_active", "title")

    @classmethod
    def get_template(cls, template_id: int) -> Content:
        return Content.objects.get(id=template_id, kind=TEMPLATE_KIND)

    @classmethod
    def save_template(cls, actor: User, payload: Dict[str, Any], template_id: Optional[int] = None) -> Content:
        normalized = _normalize_template_payload(payload)
        if template_id:
            template = cls.get_template(template_id)
        else:
            template = Content(kind=TEMPLATE_KIND, tenant=actor.tenant, created_by=actor, is_active=True)
        template.title = normalized["title"]
        template.body = normalized.get("summary") or ""
        template.category = "Onboarding Success Plan"
        template.meta = normalized
        template.save()
        return template

    @classmethod
    def duplicate_template(cls, actor: User, template_id: int) -> Content:
        source = cls.get_template(template_id)
        payload = copy.deepcopy(_normalize_template_payload(source.meta or {}))
        payload["title"] = f"{payload['title']} Copy"
        return cls.save_template(actor, payload)

    @classmethod
    def archive_template(cls, template_id: int) -> None:
        template = cls.get_template(template_id)
        template.is_active = False
        template.save(update_fields=["is_active"])

    @classmethod
    def import_templates(cls, actor: User, uploaded_file) -> int:
        raw = uploaded_file.read().decode("utf-8")
        payload = json.loads(raw)
        items = payload if isinstance(payload, list) else [payload]
        count = 0
        for item in items:
            cls.save_template(actor, item)
            count += 1
        return count

    @classmethod
    def export_template_payload(cls, template_id: int) -> Dict[str, Any]:
        template = cls.get_template(template_id)
        return _normalize_template_payload(template.meta or {})

    @classmethod
    def assign_template(cls, employee: User, template: Content, actor: User, plan_title: Optional[str] = None) -> Engagement:
        payload = _normalize_template_payload(template.meta or {})
        plan_data = _build_plan_from_template(payload, employee, actor, title=plan_title or template.title)
        engagement, _created = Engagement.objects.update_or_create(
            user=employee,
            kind=PLAN_KIND,
            defaults={
                "tenant": employee.tenant,
                "counterparty": actor,
                "content": template,
                "title": plan_data["plan_title"],
                "description": plan_data.get("summary") or "",
                "status": "active",
                "progress": 0,
                "data": plan_data,
                "is_active": True,
            },
        )
        cls.refresh_plan(employee, save=True)
        notify(
            employee,
            "Onboarding success plan assigned",
            f"Your onboarding roadmap '{engagement.title}' is ready.",
            link="/employee/onboarding-plan/",
            category="info",
        )
        return engagement

    @classmethod
    def bulk_assign_template(cls, actor: User, template: Content, employees: Iterable[User]) -> int:
        count = 0
        for employee in employees:
            cls.assign_template(employee, template, actor)
            count += 1
        return count

    @classmethod
    def create_custom_plan(cls, employee: User, actor: User, payload: Dict[str, Any]) -> Engagement:
        normalized = _normalize_template_payload(payload)
        plan_data = _build_plan_from_template(normalized, employee, actor, title=normalized["title"])
        engagement, _created = Engagement.objects.update_or_create(
            user=employee,
            kind=PLAN_KIND,
            defaults={
                "tenant": employee.tenant,
                "counterparty": actor,
                "content": None,
                "title": plan_data["plan_title"],
                "description": plan_data.get("summary") or "",
                "status": "active",
                "progress": 0,
                "data": plan_data,
                "is_active": True,
            },
        )
        cls.refresh_plan(employee, save=True)
        return engagement

    @classmethod
    def get_plan_record(cls, employee: User) -> Optional[Engagement]:
        return Engagement.objects.filter(user=employee, kind=PLAN_KIND, is_active=True).select_related("content", "counterparty").first()

    @classmethod
    def refresh_plan(cls, employee: User, save: bool = False) -> Optional[Engagement]:
        engagement = cls.get_plan_record(employee)
        if not engagement:
            return None
        data = _safe_dict(engagement.data)
        changed = False
        for phase in _safe_list(data.get("phases")):
            for section in _safe_list(phase.get("sections")):
                for activity in _safe_list(section.get("activities")):
                    auto_status = _check_automatic_completion(employee, activity)
                    if auto_status and activity.get("status") != auto_status:
                        activity["status"] = auto_status
                        activity["completed_at"] = activity.get("completed_at") or _now_iso()
                        activity.setdefault("timeline", []).append({
                            "event": "automatic_complete",
                            "label": "Completed automatically",
                            "at": _now_iso(),
                            "by_name": "System",
                        })
                        changed = True
                    if _activity_is_overdue(activity) and activity.get("status") not in {"overdue", "approved", "completed", "automatic_complete"}:
                        activity["status"] = "overdue" if activity.get("status") in {"not_started", "in_progress"} else activity.get("status")
                        changed = True
        summary = cls.build_summary(engagement, employee)
        engagement.progress = summary["overall"]["percentage"]
        if summary["overall"]["percentage"] >= 100 and engagement.status != "completed":
            engagement.status = "completed"
            engagement.completed_at = timezone.now()
            notify(employee, "Onboarding plan completed", "Congratulations on completing your success plan.", link="/employee/onboarding-plan/", category="success")
            changed = True
        data["timeline"] = summary["timeline"]
        engagement.data = data
        if save or changed:
            engagement.save(update_fields=["data", "progress", "status", "completed_at"])
        return engagement

    @classmethod
    def build_summary(cls, engagement: Engagement, employee: Optional[User] = None) -> Dict[str, Any]:
        if not engagement:
            return {}
        employee = employee or engagement.user
        data = _safe_dict(engagement.data)
        phases_out = []
        timeline = list(_safe_list(data.get("timeline")))
        upcoming = []
        overdue = []
        recent = []
        feedback = []
        total_weight = 0
        done_weight = 0
        current_phase_id = None

        for phase in _safe_list(data.get("phases")):
            phase_weight = 0
            phase_done = 0
            sections_out = []
            phase_open = False
            for section in _safe_list(phase.get("sections")):
                section_weight = 0
                section_done = 0
                activities_out = []
                for activity in _safe_list(section.get("activities")):
                    activity = _normalize_activity(activity)
                    messages = cls.get_activity_messages(employee, engagement.id, activity["id"])
                    if messages:
                        activity["messages"] = messages
                        activity["discussion_count"] = len(messages)
                        if messages[-1]["author_role"] != "employee":
                            feedback.append(messages[-1])
                    else:
                        activity["messages"] = []
                    for event in _safe_list(activity.get("timeline")):
                        timeline.append({
                            "label": event.get("label") or activity["title"],
                            "at": event.get("at") or "",
                            "phase_label": phase.get("label"),
                            "activity_title": activity["title"],
                        })
                    is_complete = _activity_completion_status(activity)
                    weight = _weight(activity.get("weight"))
                    section_weight += weight
                    phase_weight += weight
                    total_weight += weight
                    if is_complete:
                        section_done += weight
                        phase_done += weight
                        done_weight += weight
                        if activity.get("completed_at"):
                            recent.append({
                                "activity_id": activity["id"],
                                "title": activity["title"],
                                "at": activity.get("completed_at"),
                                "phase_label": phase.get("label"),
                            })
                    else:
                        phase_open = True
                        if not current_phase_id:
                            current_phase_id = phase.get("id")
                    if activity.get("due_date"):
                        try:
                            due = datetime.fromisoformat(str(activity["due_date"])).date()
                        except ValueError:
                            due = None
                        if due and not is_complete:
                            if due < timezone.now().date():
                                overdue.append({
                                    "activity_id": activity["id"],
                                    "title": activity["title"],
                                    "due_date": activity["due_date"],
                                    "phase_label": phase.get("label"),
                                })
                            elif due <= timezone.now().date() + timedelta(days=7):
                                upcoming.append({
                                    "activity_id": activity["id"],
                                    "title": activity["title"],
                                    "due_date": activity["due_date"],
                                    "phase_label": phase.get("label"),
                                })
                    activities_out.append(activity)
                sections_out.append({
                    "id": section.get("id"),
                    "label": section.get("label"),
                    "activities": activities_out,
                    "progress": cls._pct(section_done, section_weight),
                    "completed_weight": section_done,
                    "total_weight": section_weight,
                })
            phases_out.append({
                "id": phase.get("id"),
                "label": phase.get("label"),
                "description": phase.get("description"),
                "sections": sections_out,
                "progress": cls._pct(phase_done, phase_weight),
                "completed_weight": phase_done,
                "total_weight": phase_weight,
                "is_current": current_phase_id == phase.get("id") or (not current_phase_id and phase_open),
            })

        recent.sort(key=lambda item: item.get("at") or "", reverse=True)
        upcoming.sort(key=lambda item: item.get("due_date") or "")
        overdue.sort(key=lambda item: item.get("due_date") or "")
        feedback.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        timeline.sort(key=lambda item: item.get("at") or "", reverse=True)

        return {
            "overall": {
                "percentage": cls._pct(done_weight, total_weight),
                "completed_weight": done_weight,
                "total_weight": total_weight,
                "current_phase_id": current_phase_id or (phases_out[0]["id"] if phases_out else None),
            },
            "phases": phases_out,
            "upcoming": upcoming[:8],
            "overdue": overdue[:8],
            "recent_completed": recent[:8],
            "manager_feedback": feedback[:8],
            "timeline": timeline,
        }

    @staticmethod
    def _pct(done: int, total: int) -> int:
        return int(round((done / total) * 100)) if total else 0

    @classmethod
    def get_plan_context(cls, employee: User) -> Dict[str, Any]:
        engagement = cls.refresh_plan(employee, save=True)
        if not engagement:
            return {}
        summary = cls.build_summary(engagement, employee)
        template = _serialize_template_content(engagement.content) if engagement.content_id else None
        return {
            "engagement": engagement,
            "plan_data": _safe_dict(engagement.data),
            "summary": summary,
            "phases": summary.get("phases") or [],
            "template": template,
        }

    @classmethod
    def save_plan_structure(cls, engagement: Engagement, actor: User, payload: Dict[str, Any]) -> Engagement:
        existing = _safe_dict(engagement.data)
        updated = _normalize_template_payload(payload)
        plan_data = _build_plan_from_template(updated, engagement.user, actor, title=updated["title"])

        old_activities = cls._activities_by_id(existing.get("phases") or [])
        new_activities = cls._activities_by_id(plan_data.get("phases") or [])
        for aid, activity in new_activities.items():
            if aid in old_activities:
                old = old_activities[aid]
                activity["status"] = old.get("status", activity["status"])
                activity["completed_at"] = old.get("completed_at")
                activity["approved_at"] = old.get("approved_at")
                activity["returned_at"] = old.get("returned_at")
                activity["approved_by_id"] = old.get("approved_by_id")
                activity["approved_by_name"] = old.get("approved_by_name", "")
                activity["attachments"] = old.get("attachments", [])
                activity["timeline"] = old.get("timeline", [])
                activity["draft_comment"] = old.get("draft_comment", "")
                activity["last_comment_at"] = old.get("last_comment_at")
        plan_data["timeline"] = existing.get("timeline") or plan_data.get("timeline") or []
        plan_data["assigned_by_id"] = existing.get("assigned_by_id") or actor.id
        plan_data["assigned_by_name"] = existing.get("assigned_by_name") or actor.full_name
        plan_data["assigned_at"] = existing.get("assigned_at") or _now_iso()
        plan_data["employee_id"] = engagement.user_id
        plan_data["employee_joining_date"] = existing.get("employee_joining_date") or _date_iso(engagement.user.date_of_joining)
        engagement.data = plan_data
        engagement.title = plan_data["plan_title"]
        engagement.description = plan_data.get("summary") or ""
        engagement.save(update_fields=["data", "title", "description"])
        cls.refresh_plan(engagement.user, save=True)
        return engagement

    @classmethod
    def _activities_by_id(cls, phases: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        found = {}
        for phase in phases:
            for section in _safe_list(phase.get("sections")):
                for activity in _safe_list(section.get("activities")):
                    found[activity.get("id")] = activity
        return found

    @classmethod
    def _find_activity(cls, plan_data: Dict[str, Any], activity_id: str) -> Tuple[Optional[Dict], Optional[Dict], Optional[Dict]]:
        for phase in _safe_list(plan_data.get("phases")):
            for section in _safe_list(phase.get("sections")):
                for activity in _safe_list(section.get("activities")):
                    if activity.get("id") == activity_id:
                        return phase, section, activity
        return None, None, None

    @classmethod
    def add_activity_message(cls, employee: User, engagement_id: int, activity_id: str, author: User, message: str, kind: Optional[str] = None) -> ReviewMessage:
        if not kind:
            kind = "reply" if author.role == "employee" else "message"
        thread = _thread_key(engagement_id, activity_id)
        review = ReviewMessage.objects.create(
            employee=employee,
            stage=thread,
            author=author,
            message=message.strip(),
            kind=kind,
        )
        return review

    @classmethod
    def get_activity_messages(cls, employee: User, engagement_id: int, activity_id: str) -> List[Dict[str, Any]]:
        thread = _thread_key(engagement_id, activity_id)
        qs = ReviewMessage.objects.filter(employee=employee, stage=thread).select_related("author")
        return [{
            "id": msg.id,
            "message": msg.message,
            "kind": msg.kind,
            "author_id": msg.author_id,
            "author_name": msg.author.full_name if msg.author else "System",
            "author_role": msg.author.role if msg.author else "system",
            "created_at": msg.created_at.isoformat(),
        } for msg in qs]

    @classmethod
    def _save_uploaded_files(cls, files, employee: User, activity_id: str, actor: User) -> List[Dict[str, Any]]:
        uploaded = []
        for f in files:
            path = default_storage.save(
                f"onboarding_plan/{employee.id}/{activity_id}/{timezone.now():%Y%m%d%H%M%S}_{slugify(f.name)}",
                ContentFile(f.read()),
            )
            uploaded.append({
                "path": path,
                "name": f.name,
                "uploaded_by_id": actor.id,
                "uploaded_by_name": actor.full_name,
                "uploaded_at": _now_iso(),
                "url": default_storage.url(path) if hasattr(default_storage, "url") else "",
            })
        return uploaded

    @classmethod
    def update_activity(cls, engagement: Engagement, activity_id: str, actor: User, action: str,
                        comment: str = "", files=None) -> Tuple[bool, str]:
        data = _safe_dict(engagement.data)
        phase, section, activity = cls._find_activity(data, activity_id)
        if not activity:
            return False, "Activity not found."

        files = files or []
        timeline = activity.setdefault("timeline", [])
        attachments = activity.setdefault("attachments", [])
        now = _now_iso()
        uploaded = []
        if files:
            uploaded = cls._save_uploaded_files(files, engagement.user, activity_id, actor)
            attachments.extend(uploaded)

        if action == "save_draft":
            activity["status"] = "in_progress"
            activity["draft_comment"] = comment.strip()
            activity["last_comment_at"] = now
            timeline.append({"event": "draft_saved", "label": "Draft saved", "at": now, "by_name": actor.full_name})
        elif action == "mark_complete":
            if activity.get("completion_type") == "manager_approval":
                activity["status"] = "submitted"
                timeline.append({"event": "submitted", "label": "Submitted for approval", "at": now, "by_name": actor.full_name})
                notify(engagement.counterparty or engagement.user.created_by, "Plan activity submitted", f"{engagement.user.full_name} submitted '{activity['title']}' for approval.", link=f"/admin/onboarding-plans/{engagement.user_id}/", category="info")
            else:
                activity["status"] = "completed"
                activity["completed_at"] = now
                timeline.append({"event": "completed", "label": "Marked complete", "at": now, "by_name": actor.full_name})
        elif action == "approve":
            activity["status"] = "approved"
            activity["approved_at"] = now
            activity["approved_by_id"] = actor.id
            activity["approved_by_name"] = actor.full_name
            timeline.append({"event": "approved", "label": "Approved", "at": now, "by_name": actor.full_name})
            notify(engagement.user, "Plan activity approved", f"'{activity['title']}' was approved.", link="/employee/onboarding-plan/", category="success")
        elif action == "return":
            activity["status"] = "returned"
            activity["returned_at"] = now
            timeline.append({"event": "returned", "label": "Returned for changes", "at": now, "by_name": actor.full_name})
            notify(engagement.user, "Plan activity returned", f"'{activity['title']}' was returned for changes.", link="/employee/onboarding-plan/", category="warning")
        elif action == "reopen":
            activity["status"] = "in_progress"
            timeline.append({"event": "reopened", "label": "Reopened", "at": now, "by_name": actor.full_name})
        else:
            return False, "Unknown activity action."

        if comment.strip():
            cls.add_activity_message(engagement.user, engagement.id, activity_id, actor, comment.strip())
            notify(
                engagement.user if actor.id != engagement.user_id else (engagement.counterparty or engagement.user.created_by),
                "Plan activity comment",
                f"{actor.full_name} commented on '{activity['title']}'.",
                link="/employee/onboarding-plan/" if actor.id != engagement.user_id else f"/admin/onboarding-plans/{engagement.user_id}/",
                category="info",
            )

        engagement.data = data
        engagement.save(update_fields=["data"])
        cls.refresh_plan(engagement.user, save=True)
        return True, "Activity updated."

    @classmethod
    def templates_for_ui(cls, user: User) -> List[Dict[str, Any]]:
        return [_serialize_template_content(item) for item in cls.list_templates(user)]

    @classmethod
    def employees_for_assignment(cls, user: User):
        qs = User.objects.filter(role="employee").exclude(status__in=["deleted", "archived"]).select_related("department").order_by("full_name")
        if is_staff_role(user.role):
            qs = _scope_employees(user, qs)
        return qs

    @classmethod
    def active_plans_for_ui(cls, user: User) -> List[Dict[str, Any]]:
        plans = Engagement.objects.filter(kind=PLAN_KIND, user__role="employee", is_active=True).select_related("user", "content")
        if is_staff_role(user.role):
            plans = plans.filter(user__in=_scope_employees(user, User.objects.filter(role="employee")))
        items = []
        for eng in plans:
            ctx = cls.get_plan_context(eng.user)
            summary = ctx.get("summary") or {}
            items.append({
                "engagement": eng,
                "employee": eng.user,
                "summary": summary,
                "template_title": eng.content.title if eng.content_id else "Custom plan",
            })
        return items

    @classmethod
    def analytics_for_viewer(cls, user: User) -> Dict[str, Any]:
        if user.role == "employee":
            ctx = cls.get_plan_context(user)
            if not ctx:
                return {
                    "scope": "personal",
                    "has_plan": False,
                    "template_count": 0,
                    "overall_progress": 0,
                    "completed_activities": 0,
                    "overdue_activities": 0,
                    "upcoming_activities": 0,
                    "phase_breakdown": [],
                    "template_usage": [],
                    "active_plans": 0,
                    "completed_plans": 0,
                    "average_progress": 0,
                    "template_count": 0,
                }
            summary = ctx["summary"]
            total_activities = sum(
                len(section.get("activities") or [])
                for phase in summary.get("phases") or []
                for section in phase.get("sections") or []
            )
            completed_activities = sum(
                1 for phase in summary.get("phases") or []
                for section in phase.get("sections") or []
                for activity in section.get("activities") or []
                if _activity_completion_status(activity)
            )
            return {
                "scope": "personal",
                "has_plan": True,
                "overall_progress": summary["overall"]["percentage"],
                "completed_activities": completed_activities,
                "total_activities": total_activities,
                "overdue_activities": len(summary.get("overdue") or []),
                "upcoming_activities": len(summary.get("upcoming") or []),
                "phase_breakdown": [
                    {
                        "label": phase["label"],
                        "progress": phase["progress"],
                        "total_weight": phase["total_weight"],
                        "completed_weight": phase["completed_weight"],
                    }
                    for phase in summary.get("phases") or []
                ],
                "template_usage": [],
                "active_plans": 1,
                "completed_plans": 1 if ctx["engagement"].status == "completed" else 0,
                "average_progress": summary["overall"]["percentage"],
                "template_count": 1 if ctx.get("template") else 0,
            }

        plans = Engagement.objects.filter(kind=PLAN_KIND, is_active=True).select_related("user", "content")
        if is_staff_role(user.role):
            plans = plans.filter(user__in=_scope_employees(user, User.objects.filter(role="employee")))

        templates = {}
        current_phase_counts = {}
        total_progress = 0
        completed_plans = 0
        overdue_count = 0
        upcoming_count = 0
        total_activities = 0
        completed_activities = 0

        for eng in plans:
            ctx = cls.get_plan_context(eng.user)
            if not ctx:
                continue
            summary = ctx["summary"]
            total_progress += summary["overall"]["percentage"]
            if eng.status == "completed":
                completed_plans += 1
            overdue_count += len(summary.get("overdue") or [])
            upcoming_count += len(summary.get("upcoming") or [])
            template_name = eng.content.title if eng.content_id else "Custom plan"
            templates[template_name] = templates.get(template_name, 0) + 1
            phase_label = next((p["label"] for p in summary.get("phases") or [] if p.get("is_current")), "Unassigned")
            current_phase_counts[phase_label] = current_phase_counts.get(phase_label, 0) + 1
            for phase in summary.get("phases") or []:
                for section in phase.get("sections") or []:
                    for activity in section.get("activities") or []:
                        total_activities += 1
                        if _activity_completion_status(activity):
                            completed_activities += 1

        total_plans = plans.count()
        avg_progress = int(round(total_progress / total_plans)) if total_plans else 0
        phase_total = sum(current_phase_counts.values()) or 1
        template_total = sum(templates.values()) or 1

        return {
            "scope": "team" if is_staff_role(user.role) else "all",
            "has_plan": total_plans > 0,
            "active_plans": total_plans,
            "completed_plans": completed_plans,
            "average_progress": avg_progress,
            "template_count": len(templates),
            "overdue_activities": overdue_count,
            "upcoming_activities": upcoming_count,
            "completed_activities": completed_activities,
            "total_activities": total_activities,
            "template_usage": sorted(
                [{"label": k, "count": v, "share": int(round((v / template_total) * 100))} for k, v in templates.items()],
                key=lambda item: item["count"],
                reverse=True,
            )[:5],
            "phase_distribution": sorted(
                [{"label": k, "count": v, "share": int(round((v / phase_total) * 100))} for k, v in current_phase_counts.items()],
                key=lambda item: item["count"],
                reverse=True,
            )[:5],
        }


def create_plan(employee: User, creator: User, template: Dict = None) -> Engagement:
    if isinstance(template, dict):
        return OnboardingPlanService.create_custom_plan(employee, creator, template)
    if template is None:
        payload = DEFAULT_TEMPLATE_LIBRARY[0]
        return OnboardingPlanService.create_custom_plan(employee, creator, payload)
    content = template if isinstance(template, Content) else OnboardingPlanService.get_template(int(template))
    return OnboardingPlanService.assign_template(employee, content, creator)


def get_plan(employee: User) -> Optional[Dict]:
    ctx = OnboardingPlanService.get_plan_context(employee)
    return ctx.get("plan_data") if ctx else None


def get_progress_stats(employee: User) -> Dict:
    ctx = OnboardingPlanService.get_plan_context(employee)
    if not ctx:
        return {"total_milestones": 0, "completed_milestones": 0, "completion_percentage": 0, "phases": {}}
    summary = ctx["summary"]
    phase_map = {}
    total = 0
    done = 0
    for phase in summary.get("phases") or []:
        phase_total = phase["total_weight"]
        phase_done = phase["completed_weight"]
        phase_map[phase["id"]] = {
            "total": phase_total,
            "completed": phase_done,
            "percentage": phase["progress"],
            "label": phase["label"],
        }
        total += phase_total
        done += phase_done
    return {
        "total_milestones": total,
        "completed_milestones": done,
        "completion_percentage": summary["overall"]["percentage"],
        "phases": phase_map,
    }


def get_phase_status(employee: User, phase: str) -> Dict:
    ctx = OnboardingPlanService.get_plan_context(employee)
    if not ctx:
        return {}
    for item in ctx["summary"].get("phases") or []:
        if item["id"] == phase:
            return item
    return {}


def update_milestone(employee: User, phase: str, milestone_index: int, completed: bool) -> bool:
    engagement = OnboardingPlanService.get_plan_record(employee)
    if not engagement:
        return False
    ctx = OnboardingPlanService.get_plan_context(employee)
    phases = ctx["summary"].get("phases") or []
    target_phase = next((p for p in phases if p["id"] == phase), None)
    if not target_phase:
        return False
    activities = []
    for section in target_phase.get("sections") or []:
        activities.extend(section.get("activities") or [])
    if milestone_index < 0 or milestone_index >= len(activities):
        return False
    action = "mark_complete" if completed else "reopen"
    ok, _msg = OnboardingPlanService.update_activity(engagement, activities[milestone_index]["id"], employee, action)
    return ok


def post_update(employee: User, phase: str, author: User, message: str, author_role: str = None) -> bool:
    ctx = OnboardingPlanService.get_plan_context(employee)
    if not ctx:
        return False
    engagement = ctx["engagement"]
    target_phase = next((p for p in ctx["summary"].get("phases") or [] if p["id"] == phase), None)
    if not target_phase:
        return False
    first_activity = None
    for section in target_phase.get("sections") or []:
        acts = section.get("activities") or []
        if acts:
            first_activity = acts[0]
            break
    if not first_activity:
        return False
    OnboardingPlanService.add_activity_message(employee, engagement.id, first_activity["id"], author, message)
    return True
