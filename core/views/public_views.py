"""Public (unauthenticated) form submission."""
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from ..models import Form, FormResponse


@require_http_methods(["GET", "POST"])
def public_form(request, token):
    form = get_object_or_404(Form, share_token=token, is_active=True)

    # Respect open/close window if configured.
    now = timezone.now()
    if (form.start_date and now < form.start_date) or (form.end_date and now > form.end_date):
        return render(request, "public/form_closed.html", {"form": form})

    if request.method == "POST":
        answers, files = {}, {}
        for field in form.get_all_fields():
            name = field["field_name"]
            key = f"field_{name}"
            if field.get("field_type") == "checkbox":
                answers[name] = request.POST.getlist(key)
            else:
                answers[name] = request.POST.get(key, "")
        FormResponse.objects.create(
            form=form,
            employee=None,
            answers=answers,
            files=files,
            is_draft=False,
            respondent_name=(request.POST.get("respondent_name") or "").strip() or None,
            respondent_email=(request.POST.get("respondent_email") or "").strip() or None,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        return redirect("public_thank_you")

    return render(request, "public/form_view.html", {"form": form})


def thank_you(request):
    return render(request, "public/thank_you.html")
