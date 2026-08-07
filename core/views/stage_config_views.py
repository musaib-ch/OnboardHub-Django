"""
Stage and workflow template management views (Setup → Stages/Templates).
"""
from django.contrib import messages
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from ..decorators import permission_required
from .. import pipeline
from .. import pipeline_v2
from ..models import StageDefinition, StageTemplate
from ..services import log_activity
from ..pipeline_v2 import clear_stage_cache


# ─────────────────────────────────────────────────────────────────────────────
# STAGE DEFINITIONS MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

def _code_stage_options():
    """Return the portal stage catalog in the same order used by code."""
    existing_keys = set(StageDefinition.objects.values_list("stage_key", flat=True))
    return [
        {
            "key": key,
            "label": pipeline.STAGE_LABELS.get(key, key.replace("_", " ").title()),
            "exists": key in existing_keys,
        }
        for key in pipeline.STAGE_ORDER
    ]


def _template_stage_options(include_selected=None):
    """Return only code-defined stages that are currently enabled."""
    include_selected = set(include_selected or [])
    enabled_defs = {
        stage.stage_key: stage
        for stage in StageDefinition.objects.filter(is_enabled=True).order_by("order")
    }
    options = []
    for option in _code_stage_options():
        key = option["key"]
        stage_def = enabled_defs.get(key)
        if stage_def or key in include_selected:
            options.append(option)
            if stage_def:
                option["description"] = stage_def.description
                option["enabled"] = stage_def.is_enabled
            else:
                option["description"] = ""
                option["enabled"] = False
    return options


@permission_required("manage_stages")
@require_http_methods(["GET", "POST"])
def stages_list(request):
    """List all stage definitions with enable/disable toggles."""
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "toggle":
            stage_id = request.POST.get("stage_id")
            stage = get_object_or_404(StageDefinition, id=stage_id)
            stage.is_enabled = not stage.is_enabled
            stage.save(update_fields=["is_enabled"])
            clear_stage_cache()
            status = "enabled" if stage.is_enabled else "disabled"
            messages.success(request, f"Stage '{stage.label}' has been {status}.")
            log_activity(request, action="toggle_stage", entity_type="stage", entity_id=stage.id,
                        description=f"Toggled {stage.stage_key} to {status}")

        elif action == "reorder":
            # Handle reordering stages
            order_data = request.POST.get("order_data")  # JSON list of stage IDs in order
            import json
            try:
                order_list = json.loads(order_data)
                for idx, stage_id in enumerate(order_list):
                    stage = StageDefinition.objects.get(id=int(stage_id))
                    stage.order = idx
                    stage.save(update_fields=["order"])
                clear_stage_cache()
                messages.success(request, "Stage order updated.")
                log_activity(request, action="reorder_stages", entity_type="stage",
                            description="Reordered stages")
            except (json.JSONDecodeError, ValueError, StageDefinition.DoesNotExist):
                messages.error(request, "Invalid order data.")

        return redirect("admin_stages_list")

    stages = StageDefinition.objects.order_by("order")
    enabled_count = stages.filter(is_enabled=True).count()
    return render(request, "admin/setup/stages_list.html", {
        "stages": stages,
        "enabled_count": enabled_count,
        "disabled_count": stages.count() - enabled_count,
        "stage_catalog": _code_stage_options(),
    })


@permission_required("manage_stages")
@require_http_methods(["GET", "POST"])
def stage_create(request):
    """Create a new custom stage."""
    if request.method == "POST":
        stage_key = (request.POST.get("stage_key") or "").strip().lower().replace(" ", "_")
        label = (request.POST.get("label") or "").strip()
        description = (request.POST.get("description") or "").strip()
        default_due_date_days = request.POST.get("default_due_date_days", "7")
        is_mandatory = request.POST.get("is_mandatory") == "on"
        stage_type = request.POST.get("stage_type", "optional")

        # Validate
        if not stage_key or not label:
            messages.error(request, "Stage key and label are required.")
            return redirect("admin_stage_create")

        allowed_stage_keys = {option["key"] for option in _code_stage_options()}
        if stage_key not in allowed_stage_keys:
            messages.error(request, "Please select one of the code-defined stage keys.")
            return redirect("admin_stage_create")

        if StageDefinition.objects.filter(stage_key=stage_key).exists():
            messages.error(request, f"A stage with key '{stage_key}' already exists.")
            return redirect("admin_stage_create")

        try:
            due_days = int(default_due_date_days)
            if due_days < 1:
                raise ValueError()
        except ValueError:
            messages.error(request, "Due date days must be a positive integer.")
            return redirect("admin_stage_create")

        # Get next order number
        last_order = StageDefinition.objects.aggregate(models.Max("order"))["order__max"] or -1
        next_order = last_order + 1

        stage = StageDefinition.objects.create(
            stage_key=stage_key,
            label=label,
            description=description,
            default_due_date_days=due_days,
            is_mandatory=is_mandatory,
            stage_type=stage_type,
            order=next_order,
            created_by=request.user,
        )

        clear_stage_cache()
        messages.success(request, f"Stage '{label}' created successfully.")
        log_activity(request, action="create_stage", entity_type="stage", entity_id=stage.id,
                    description=f"Created stage {stage_key}")
        return redirect("admin_stages_list")

    return render(request, "admin/setup/stage_create.html", {
        "stage_catalog": _code_stage_options(),
    })


@permission_required("manage_stages")
@require_http_methods(["GET", "POST"])
def stage_edit(request, stage_id):
    """Edit a stage definition."""
    stage = get_object_or_404(StageDefinition, id=stage_id)

    if request.method == "POST":
        stage.label = (request.POST.get("label") or "").strip()
        stage.description = (request.POST.get("description") or "").strip()

        try:
            due_days = int(request.POST.get("default_due_date_days", "7"))
            if due_days < 1:
                raise ValueError()
            stage.default_due_date_days = due_days
        except ValueError:
            messages.error(request, "Due date days must be a positive integer.")
            return redirect("admin_stage_edit", stage_id=stage.id)

        stage.is_mandatory = request.POST.get("is_mandatory") == "on"
        stage.stage_type = request.POST.get("stage_type", "optional")
        stage.save()

        clear_stage_cache()
        messages.success(request, f"Stage '{stage.label}' updated.")
        log_activity(request, action="edit_stage", entity_type="stage", entity_id=stage.id,
                    description=f"Updated stage {stage.stage_key}")
        return redirect("admin_stages_list")

    return render(request, "admin/setup/stage_edit.html", {
        "stage": stage,
    })


# ─────────────────────────────────────────────────────────────────────────────
# STAGE TEMPLATES MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@permission_required("manage_stage_templates")
@require_http_methods(["GET"])
def templates_list(request):
    """List all stage templates."""
    templates = StageTemplate.objects.order_by("name")
    return render(request, "admin/setup/templates_list.html", {
        "templates": templates,
    })


@permission_required("manage_stage_templates")
@require_http_methods(["GET", "POST"])
def template_create(request):
    """Create a new stage template."""
    from ..models import StageDefinition

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        description = (request.POST.get("description") or "").strip()
        selected_stages = request.POST.getlist("stages")
        allowed_stage_keys = {option["key"] for option in _template_stage_options()}
        selected_stages = [stage for stage in selected_stages if stage in allowed_stage_keys]

        if not name:
            messages.error(request, "Template name is required.")
            return redirect("admin_template_create")

        if StageTemplate.objects.filter(name=name).exists():
            messages.error(request, f"A template named '{name}' already exists.")
            return redirect("admin_template_create")

        if not selected_stages:
            messages.error(request, "At least one stage must be selected.")
            return redirect("admin_template_create")

        template = StageTemplate.objects.create(
            name=name,
            description=description,
            stages=selected_stages,
            created_by=request.user,
        )

        messages.success(request, f"Template '{name}' created successfully.")
        log_activity(request, action="create_template", entity_type="template", entity_id=template.id,
                    description=f"Created template {name}")
        return redirect("admin_templates_list")

    return render(request, "admin/setup/template_create.html", {
        "stage_options": _template_stage_options(),
        "selected_stage_keys": [],
    })


@permission_required("manage_stage_templates")
@require_http_methods(["GET", "POST"])
def template_edit(request, template_id):
    """Edit a stage template."""
    from ..models import StageDefinition

    template = get_object_or_404(StageTemplate, id=template_id)

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        description = (request.POST.get("description") or "").strip()
        selected_stages = request.POST.getlist("stages")
        allowed_stage_keys = {option["key"] for option in _template_stage_options(template.stages)}
        selected_stages = [stage for stage in selected_stages if stage in allowed_stage_keys]

        if not name:
            messages.error(request, "Template name is required.")
            return redirect("admin_template_edit", template_id=template.id)

        if not selected_stages:
            messages.error(request, "At least one stage must be selected.")
            return redirect("admin_template_edit", template_id=template.id)

        template.name = name
        template.description = description
        template.stages = selected_stages
        template.save()

        messages.success(request, f"Template '{name}' updated.")
        log_activity(request, action="edit_template", entity_type="template", entity_id=template.id,
                    description=f"Updated template {name}")
        return redirect("admin_templates_list")

    return render(request, "admin/setup/template_edit.html", {
        "template": template,
        "stage_options": _template_stage_options(template.stages),
        "selected_stage_keys": template.stages,
    })


@permission_required("manage_stage_templates")
@require_http_methods(["POST"])
def template_delete(request, template_id):
    """Delete a stage template."""
    template = get_object_or_404(StageTemplate, id=template_id)
    name = template.name
    template.delete()

    messages.success(request, f"Template '{name}' deleted.")
    log_activity(request, action="delete_template", entity_type="template",
                description=f"Deleted template {name}")
    return redirect("admin_templates_list")


@permission_required("manage_stage_templates")
@require_http_methods(["POST"])
def template_set_default(request, template_id):
    """Set a template as the default for new employees (only one can be default)."""
    from ..models import AppSetting

    template = get_object_or_404(StageTemplate, id=template_id)

    # Unset all other templates from being global (only one can be default)
    StageTemplate.objects.exclude(id=template_id).update(is_global=False)

    # Set this template as the default
    template.is_global = True
    template.save(update_fields=['is_global'])

    AppSetting.set("default_stage_template", template.name)

    messages.success(request, f"'{template.name}' is now the default template. All other templates set to non-default.")
    log_activity(request, action="set_default_template", entity_type="template", entity_id=template.id,
                description=f"Set default template to {template.name} (unset all others)")
    return redirect("admin_templates_list")
