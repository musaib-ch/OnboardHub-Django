"""Lightweight automation + reminder engine — rules stored in AppSetting JSON.

  automation_rules: [{name, trigger(status), action, message, active}]
      fired when an employee's status changes TO `trigger`.
  reminder_rules:   [{name, status, days, message, active}]
      run by `manage.py run_reminders` (cron) for employees stuck in a status.

No new tables — rules live in AppSetting; reminders dedupe via the Notification table.
"""
import datetime
import json

from django.utils import timezone

from .models import AppSetting, User, Notification
from .services import notify

AUTOMATION_KEY = "automation_rules"
REMINDER_KEY = "reminder_rules"

ACTIONS = [
    ("notify_employee", "Notify the employee (in-app + email)"),
    ("notify_admins", "Notify admins"),
]


def get_rules(key):
    raw = AppSetting.get(key)
    try:
        data = json.loads(raw) if raw else []
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


def save_rules(key, rules, user=None):
    AppSetting.set(key, json.dumps(rules), user=user)


def _fill(text, emp, status):
    return ((text or "")
            .replace("{full_name}", emp.full_name or "")
            .replace("{stage}", (status or "").replace("_", " ").title()))


# ── Event automation (fired by the User status-change signal) ────────────────
def fire_status_change(emp, old_status, new_status):
    if getattr(emp, "role", None) != "employee" or old_status == new_status:
        return
    # Finishing onboarding auto-assigns any matching post-onboarding training.
    if new_status == "completed":
        try:
            from .views.training_views import apply_assignment_rules
            apply_assignment_rules(user=emp)
        except Exception:
            pass  # never block the status change
    for rule in get_rules(AUTOMATION_KEY):
        if not rule.get("active", True) or rule.get("trigger") != new_status:
            continue
        title = rule.get("name") or "Onboarding update"
        msg = _fill(rule.get("message"), emp, new_status)
        action = rule.get("action", "notify_employee")
        if action == "notify_admins":
            for admin in User.objects.filter(role__in=["super_admin", "admin"], is_active=True):
                notify(admin, title, f"{emp.full_name}: {msg}", link=f"/admin/employees/{emp.id}/")
        else:
            notify(emp, title, msg, link="/employee/home/")


# ── Time-based reminders (run via management command) ────────────────────────
def run_reminders():
    rules = [r for r in get_rules(REMINDER_KEY) if r.get("active", True)]
    sent = 0
    now = timezone.now()
    for rule in rules:
        status = rule.get("status")
        try:
            days = int(rule.get("days") or 0)
        except (ValueError, TypeError):
            days = 0
        if not status:
            continue
        cutoff = now - datetime.timedelta(days=days)
        title = rule.get("name") or "Reminder"
        emps = User.objects.filter(role="employee", status=status, updated_at__lte=cutoff)
        for emp in emps:
            # Don't re-send the same reminder within 20 hours.
            if Notification.objects.filter(
                user=emp, title=title, created_at__gte=now - datetime.timedelta(hours=20)
            ).exists():
                continue
            notify(emp, title, _fill(rule.get("message"), emp, status), link="/employee/home/")
            sent += 1
    return sent
