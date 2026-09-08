"""System audit log views for super administrators."""
import csv
import io

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from ..decorators import roles_required
from ..models import AuditLog, User


@roles_required("super_admin")
@require_GET
def system_logs(request):
    """Unified audit, email, notification and portal-action log."""
    qs = AuditLog.objects.select_related("user").all()

    log_type = (request.GET.get("type") or "").strip().lower()
    status = (request.GET.get("status") or "").strip().lower()
    action = (request.GET.get("action") or "").strip()
    entity_type = (request.GET.get("entity_type") or "").strip()
    user_id = (request.GET.get("user_id") or "").strip()
    search = (request.GET.get("q") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    if log_type == "email":
        qs = qs.filter(entity_type="email")
    elif log_type == "notification":
        qs = qs.filter(entity_type="notification")
    elif log_type == "action":
        qs = qs.exclude(entity_type__in=["email", "notification"])
    elif log_type == "error":
        qs = qs.filter(action__icontains="failed")

    if status == "success":
        qs = qs.exclude(action__icontains="failed").exclude(description__icontains=" failed ")
    elif status == "failed":
        qs = qs.filter(action__icontains="failed") | qs.filter(description__icontains=" failed ")

    if action:
        qs = qs.filter(action__icontains=action)
    if entity_type:
        qs = qs.filter(entity_type__icontains=entity_type)
    if user_id.isdigit():
        qs = qs.filter(user_id=int(user_id))
    if search:
        qs = qs.filter(description__icontains=search) | qs.filter(action__icontains=search)
    if date_from:
        qs = qs.filter(timestamp__date__gte=date_from)
    if date_to:
        qs = qs.filter(timestamp__date__lte=date_to)

    qs = qs.order_by("-timestamp")
    if request.GET.get("export") == "csv":
        return _export_csv(qs)

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    return render(request, "admin/system_logs.html", {
        "logs": page_obj,
        "users": User.objects.filter(is_active=True).order_by("full_name", "email"),
        "filters": {
            "type": log_type,
            "status": status,
            "action": action,
            "entity_type": entity_type,
            "user_id": user_id,
            "q": search,
            "date_from": date_from,
            "date_to": date_to,
        },
        "total_count": paginator.count,
    })


def _export_csv(qs):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "User", "Action", "Type", "Entity ID", "IP", "Description"])
    for log in qs.iterator():
        writer.writerow([
            timezone.localtime(log.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            log.user.email if log.user_id else "System",
            log.action,
            log.entity_type or "",
            log.entity_id or "",
            log.ip_address or "",
            log.description or "",
        ])
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="onboardhub_system_logs.csv"'
    return response
