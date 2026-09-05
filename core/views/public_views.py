"""Public (unauthenticated) form submission."""
import bleach
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from ..models import Form, FormResponse


@require_http_methods(["GET", "POST"])
def public_form(request, token):
    # Lookup by token only (never by raw ID — prevents enumeration)
    form = Form.objects.filter(share_token=token).first()

    if not form:
        return render(request, "public/form_closed.html", {
            "title": "Form Not Found",
            "message": "The requested form or survey link does not exist or has been removed."
        })

    # Auto-generate share_token if missing
    if not form.share_token:
        form.generate_share_token()
        form.save(update_fields=["share_token"])

    if not form.is_active:
        return render(request, "public/form_closed.html", {
            "form": form,
            "title": "Form Inactive",
            "message": f"The form '{form.name}' is currently inactive and not accepting responses."
        })

    # Respect open/close window if configured.
    now = timezone.now()
    if (form.start_date and now < form.start_date) or (form.end_date and now > form.end_date):
        return render(request, "public/form_closed.html", {
            "form": form,
            "title": "Submissions Closed",
            "message": f"The submission period for '{form.name}' has ended."
        })

    if request.method == "POST":
        answers = {}
        for field in form.get_all_fields():
            name = field["field_name"]
            key = f"field_{name}"
            if field.get("field_type") == "checkbox":
                answers[name] = request.POST.getlist(key)
            else:
                # Sanitize free-text answers to strip any HTML/script tags
                raw = request.POST.get(key, "")
                answers[name] = bleach.clean(raw, tags=[], strip=True)

        # Sanitize respondent identity fields
        respondent_name = bleach.clean(
            (request.POST.get("respondent_name") or "").strip(), tags=[], strip=True
        ) or None
        respondent_email = bleach.clean(
            (request.POST.get("respondent_email") or "").strip(), tags=[], strip=True
        ) or None

        ip_address = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR")
        )

        FormResponse.objects.create(
            form=form,
            employee=None,
            answers=answers,
            files={},
            is_draft=False,
            respondent_name=respondent_name,
            respondent_email=respondent_email,
            ip_address=ip_address,
        )
        return redirect("public_thank_you")

    return render(request, "public/form_view.html", {"form": form})


def thank_you(request):
    return render(request, "public/thank_you.html")
