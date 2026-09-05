import json
from datetime import timedelta
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseNotAllowed, HttpResponseForbidden, HttpResponse, HttpResponseServerError
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.encoding import smart_str
import time
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from ..decorators import login_required
from ..models_offers import OfferTemplate, OfferEmailTemplate, OfferFieldDefinition, OfferAttachment, Offer, OfferFieldValue, OfferStatusHistory, OfferSendToken, OfferApproval
from django.template import engines
from django.conf import settings
import os


def _serialize_template(obj: OfferTemplate):
    return {
        'id': obj.id,
        'tenant_id': obj.tenant_id,
        'name': obj.name,
        'description': obj.description,
        'html_content': obj.html_content,
        'plain_text_preview': obj.plain_text_preview,
        'is_default': obj.is_default,
        'variables_schema': obj.variables_schema,
        'attachments_allowed': obj.attachments_allowed,
        'created_by_id': obj.created_by_id,
        'created_at': obj.created_at.isoformat() if obj.created_at else None,
        'updated_at': obj.updated_at.isoformat() if obj.updated_at else None,
    }


def _serialize_email_template(obj: OfferEmailTemplate):
    return {
        'id': obj.id,
        'tenant_id': obj.tenant_id,
        'name': obj.name,
        'subject_template': obj.subject_template,
        'html_body_template': obj.html_body_template,
        'plain_text_template': obj.plain_text_template,
        'created_by_id': obj.created_by_id,
        'created_at': obj.created_at.isoformat() if obj.created_at else None,
        'updated_at': obj.updated_at.isoformat() if obj.updated_at else None,
    }


@login_required
@require_http_methods(['GET', 'POST'])
def offer_templates_list(request):
    # Permission: manage_templates to create, view allowed to any logged-in staff
    if request.method == 'GET':
        qs = OfferTemplate.objects.filter(tenant=request.user.tenant) if request.user.tenant else OfferTemplate.objects.all()
        data = [_serialize_template(t) for t in qs.order_by('-is_default', 'name')]
        return JsonResponse({'templates': data})

    if request.method == 'POST':
        if not request.user.has_perm_key('manage_templates'):
            return HttpResponseForbidden('Insufficient permissions')
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return HttpResponseBadRequest('Invalid JSON payload')
        name = payload.get('name')
        if not name:
            return HttpResponseBadRequest('Template name is required')
        tpl = OfferTemplate.objects.create(
            tenant=request.user.tenant,
            name=name,
            description=payload.get('description', ''),
            html_content=payload.get('html_content', ''),
            plain_text_preview=payload.get('plain_text_preview', ''),
            created_by=request.user,
            is_default=bool(payload.get('is_default', False)),
            variables_schema=payload.get('variables_schema') or {},
            attachments_allowed=bool(payload.get('attachments_allowed', True)),
        )
        return JsonResponse({'template': _serialize_template(tpl)}, status=201)


@login_required
@require_http_methods(['GET', 'PUT', 'PATCH', 'DELETE'])
def offer_template_detail(request, template_id):
    tpl = get_object_or_404(OfferTemplate, id=template_id)
    # Tenant isolation
    if request.user.tenant and tpl.tenant_id != request.user.tenant.id:
        return HttpResponseForbidden('Not found')

    if request.method == 'GET':
        return JsonResponse({'template': _serialize_template(tpl)})

    if request.method in ('PUT', 'PATCH'):
        if not request.user.has_perm_key('manage_templates'):
            return HttpResponseForbidden('Insufficient permissions')
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return HttpResponseBadRequest('Invalid JSON payload')
        changed = False
        for field in ('name', 'description', 'html_content', 'plain_text_preview', 'is_default', 'variables_schema', 'attachments_allowed'):
            if field in payload:
                setattr(tpl, field, payload[field])
                changed = True
        if changed:
            tpl.save()
        return JsonResponse({'template': _serialize_template(tpl)})

    if request.method == 'DELETE':
        if not request.user.has_perm_key('manage_templates'):
            return HttpResponseForbidden('Insufficient permissions')
        tpl.delete()
        return JsonResponse({'deleted': True})


# Email templates
@login_required
@require_http_methods(['GET', 'POST'])
def email_templates_list(request):
    if request.method == 'GET':
        qs = OfferEmailTemplate.objects.filter(tenant=request.user.tenant) if request.user.tenant else OfferEmailTemplate.objects.all()
        data = [_serialize_email_template(t) for t in qs.order_by('name')]
        return JsonResponse({'email_templates': data})

    if request.method == 'POST':
        if not request.user.has_perm_key('manage_email_templates'):
            return HttpResponseForbidden('Insufficient permissions')
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return HttpResponseBadRequest('Invalid JSON payload')
        name = payload.get('name')
        subject = payload.get('subject_template', '')
        if not name:
            return HttpResponseBadRequest('Template name is required')
        tpl = OfferEmailTemplate.objects.create(
            tenant=request.user.tenant,
            name=name,
            subject_template=subject,
            html_body_template=payload.get('html_body_template', ''),
            plain_text_template=payload.get('plain_text_template', ''),
            created_by=request.user,
        )
        return JsonResponse({'email_template': _serialize_email_template(tpl)}, status=201)


@login_required
@require_http_methods(['GET', 'PUT', 'PATCH', 'DELETE'])
def email_template_detail(request, template_id):
    tpl = get_object_or_404(OfferEmailTemplate, id=template_id)
    if request.user.tenant and tpl.tenant_id != request.user.tenant.id:
        return HttpResponseForbidden('Not found')

    if request.method == 'GET':
        return JsonResponse({'email_template': _serialize_email_template(tpl)})

    if request.method in ('PUT', 'PATCH'):
        if not request.user.has_perm_key('manage_email_templates'):
            return HttpResponseForbidden('Insufficient permissions')
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return HttpResponseBadRequest('Invalid JSON payload')
        changed = False
        for field in ('name', 'subject_template', 'html_body_template', 'plain_text_template'):
            if field in payload:
                setattr(tpl, field, payload[field])
                changed = True
        if changed:
            tpl.save()
        return JsonResponse({'email_template': _serialize_email_template(tpl)})

    if request.method == 'DELETE':
        if not request.user.has_perm_key('manage_email_templates'):
            return HttpResponseForbidden('Insufficient permissions')
        tpl.delete()
        return JsonResponse({'deleted': True})


# Offer field definitions (org-configurable fields)
@login_required
@require_http_methods(['GET', 'POST'])
def offer_fields_list(request):
    if request.method == 'GET':
        qs = OfferFieldDefinition.objects.filter(tenant=request.user.tenant) if request.user.tenant else OfferFieldDefinition.objects.all()
        data = [
            {
                'id': f.id,
                'name': f.name,
                'key': f.key,
                'field_type': f.field_type,
                'required': f.required,
                'visible_to': f.visible_to,
                'order': f.order,
                'meta': f.meta,
            }
            for f in qs.order_by('order', 'name')
        ]
        return JsonResponse({'fields': data})

    # POST
    if not request.user.has_perm_key('manage_offer_fields'):
        return HttpResponseForbidden('Insufficient permissions')
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return HttpResponseBadRequest('Invalid JSON payload')
    name = payload.get('name')
    key = payload.get('key')
    if not name or not key:
        return HttpResponseBadRequest('name and key are required')
    field = OfferFieldDefinition.objects.create(
        tenant=request.user.tenant,
        name=name,
        key=key,
        field_type=payload.get('field_type', 'string'),
        required=bool(payload.get('required', False)),
        visible_to=payload.get('visible_to') or [],
        order=int(payload.get('order') or 0),
        meta=payload.get('meta') or {},
    )
    return JsonResponse({'field': {'id': field.id, 'name': field.name, 'key': field.key}}, status=201)


@login_required
@require_http_methods(['GET', 'PUT', 'PATCH', 'DELETE'])
def offer_field_detail(request, field_id):
    f = get_object_or_404(OfferFieldDefinition, id=field_id)
    if request.user.tenant and f.tenant_id != request.user.tenant.id:
        return HttpResponseForbidden('Not found')

    if request.method == 'GET':
        return JsonResponse({'field': {'id': f.id, 'name': f.name, 'key': f.key, 'field_type': f.field_type, 'required': f.required, 'visible_to': f.visible_to, 'order': f.order, 'meta': f.meta}})

    if request.method in ('PUT', 'PATCH'):
        if not request.user.has_perm_key('manage_offer_fields'):
            return HttpResponseForbidden('Insufficient permissions')
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return HttpResponseBadRequest('Invalid JSON payload')
        changed = False
        for field in ('name', 'key', 'field_type', 'required', 'visible_to', 'order', 'meta'):
            if field in payload:
                setattr(f, field, payload[field])
                changed = True
        if changed:
            f.save()
        return JsonResponse({'field': {'id': f.id, 'name': f.name, 'key': f.key}})

    if request.method == 'DELETE':
        if not request.user.has_perm_key('manage_offer_fields'):
            return HttpResponseForbidden('Insufficient permissions')
        f.delete()
        return JsonResponse({'deleted': True})


# Image upload endpoint for WYSIWYG paste uploads
@login_required
@require_http_methods(['POST'])
def offer_image_upload(request):
    # Require manage_templates permission to upload images for templates
    if not request.user.has_perm_key('manage_templates'):
        return HttpResponseForbidden('Insufficient permissions')
    if 'file' not in request.FILES:
        return HttpResponseBadRequest('No file provided')
    up = request.FILES['file']
    # Basic validation: limit size to 5MB and only common image types
    if up.size > 5 * 1024 * 1024:
        return HttpResponseBadRequest('File too large')
    allowed = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
    if up.content_type not in allowed:
        return HttpResponseBadRequest('Unsupported file type')
    # Save file to media and create OfferAttachment record attached to no offer (template upload)
    subdir = 'offer_images'
    # Sanitize filename to prevent path traversal
    import uuid as _uuid
    safe_ext = up.name.rsplit('.', 1)[-1].lower() if '.' in up.name else 'bin'
    safe_name = f"{_uuid.uuid4().hex}.{safe_ext}"
    name = default_storage.save(os.path.join(subdir, safe_name), ContentFile(up.read()))
    url = default_storage.url(name)
    att = OfferAttachment.objects.create(
        template=None,
        offer=None,
        file=name,
        filename=os.path.basename(name),
        content_type=up.content_type,
        size=up.size,
        uploaded_by=request.user,
    )
    return JsonResponse({'url': url, 'filename': att.filename})


# Template preview endpoint: render template with provided context (or sample)
@login_required
@require_http_methods(['POST'])
def offer_template_preview(request, template_id):
    tpl = get_object_or_404(OfferTemplate, id=template_id)
    if request.user.tenant and tpl.tenant_id != request.user.tenant.id:
        return HttpResponseForbidden('Not found')
    if not request.user.has_perm_key('manage_templates'):
        return HttpResponseForbidden('Insufficient permissions')
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        payload = {}
    context = payload.get('context') or {
        'candidate_name': 'Jane Doe',
        'candidate_email': 'jane@example.com',
    }
    # Use Django template engine to render the HTML content safely
    django_engine = engines['django']
    template = django_engine.from_string(tpl.html_content or '')
    rendered = template.render(context)
    return JsonResponse({'rendered_html': rendered})


# Offers CRUD
@login_required
@require_http_methods(['GET', 'POST'])
def offers_list(request):
    if request.method == 'GET':
        qs = Offer.objects.filter(tenant=request.user.tenant) if request.user.tenant else Offer.objects.all()
        data = []
        for o in qs.order_by('-created_at'):
            data.append({
                'id': o.id,
                'candidate_name': o.candidate_name,
                'candidate_email': o.candidate_email,
                'status': o.status,
                'sent_at': o.sent_at.isoformat() if o.sent_at else None,
                'created_at': o.created_at.isoformat() if o.created_at else None,
            })
        return JsonResponse({'offers': data})

    # POST - create draft offer
    if not request.user.has_perm_key('send_offer'):
        # allow creators who can manage offers or have manage_templates? Use send_offer as baseline
        return HttpResponseForbidden('Insufficient permissions')
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return HttpResponseBadRequest('Invalid JSON payload')
    candidate_name = payload.get('candidate_name')
    candidate_email = payload.get('candidate_email')
    if not candidate_name or not candidate_email:
        return HttpResponseBadRequest('candidate_name and candidate_email are required')
    tpl_id = payload.get('template_id')
    template = None
    if tpl_id:
        template = OfferTemplate.objects.filter(id=tpl_id).first()
        if template and request.user.tenant and template.tenant_id != request.user.tenant.id:
            template = None
    # Allow selecting an email template per-offer
    email_template_id = payload.get('email_template_id')
    email_template = None
    if email_template_id:
        email_template = OfferEmailTemplate.objects.filter(id=email_template_id).first()
        if email_template and request.user.tenant and email_template.tenant_id != request.user.tenant.id:
            email_template = None

    offer = Offer.objects.create(
        tenant=request.user.tenant,
        template=template,
        email_template=email_template,
        created_by=request.user,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        status='draft',
    )
    # field_values: dict key->value
    fv = payload.get('field_values') or {}
    # create OfferFieldValue for known definitions
    for key, val in fv.items():
        field_def = OfferFieldDefinition.objects.filter(tenant=request.user.tenant, key=key).first()
        # store as text; numeric/date parsing could be added
        OfferFieldValue.objects.create(offer=offer, field_definition=field_def, value=str(val) if val is not None else '')
    return JsonResponse({'offer_id': offer.id, 'status': offer.status, 'email_template_id': email_template.id if email_template else None}, status=201)


@login_required
@require_http_methods(['GET', 'PUT', 'PATCH', 'DELETE'])
def offer_detail(request, offer_id):
    o = get_object_or_404(Offer, id=offer_id)
    if request.user.tenant and o.tenant_id != request.user.tenant.id:
        return HttpResponseForbidden('Not found')
    if request.method == 'GET':
        fields = {fv.field_definition.key if fv.field_definition else None: fv.value for fv in o.field_values.all()}
        return JsonResponse({'offer': {
            'id': o.id,
            'candidate_name': o.candidate_name,
            'candidate_email': o.candidate_email,
            'status': o.status,
            'rendered_html': o.rendered_html,
            'field_values': fields,
            'email_template_id': o.email_template_id,
            'created_at': o.created_at.isoformat(),
        }})

    if request.method in ('PUT', 'PATCH'):
        if not request.user.has_perm_key('send_offer'):
            return HttpResponseForbidden('Insufficient permissions')
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return HttpResponseBadRequest('Invalid JSON payload')
        changed = False
        for field in ('candidate_name', 'candidate_email', 'template', 'email_template'):
            if field in payload:
                if field == 'template':
                    tpl = OfferTemplate.objects.filter(id=payload.get('template')).first()
                    if tpl and request.user.tenant and tpl.tenant_id != request.user.tenant.id:
                        continue
                    o.template = tpl
                elif field == 'email_template':
                    et = OfferEmailTemplate.objects.filter(id=payload.get('email_template')).first()
                    if et and request.user.tenant and et.tenant_id != request.user.tenant.id:
                        continue
                    o.email_template = et
                else:
                    setattr(o, field, payload[field])
                changed = True
        if 'field_values' in payload:
            fv = payload.get('field_values') or {}
            # simple strategy: delete existing and recreate
            o.field_values.all().delete()
            for key, val in fv.items():
                field_def = OfferFieldDefinition.objects.filter(tenant=request.user.tenant, key=key).first()
                OfferFieldValue.objects.create(offer=o, field_definition=field_def, value=str(val) if val is not None else '')
            changed = True
        if changed:
            o.save()
        return JsonResponse({'offer_id': o.id, 'status': o.status, 'email_template_id': o.email_template_id})

    if request.method == 'DELETE':
        if not request.user.has_perm_key('send_offer'):
            return HttpResponseForbidden('Insufficient permissions')
        o.delete()
        return JsonResponse({'deleted': True})


# Render an offer with provided field values (without saving)
@login_required
@require_http_methods(['POST'])
def offer_render_preview(request, offer_id=None):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        payload = {}
    # allow preview for a template or an existing offer
    if offer_id:
        o = get_object_or_404(Offer, id=offer_id)
        tpl = o.template
        base_context = {
            'candidate_name': o.candidate_name,
            'candidate_email': o.candidate_email,
        }
        # include existing field values
        for fv in o.field_values.all():
            key = fv.field_definition.key if fv.field_definition else None
            if key:
                base_context[key] = fv.value
    else:
        tpl_id = payload.get('template_id')
        tpl = OfferTemplate.objects.filter(id=tpl_id).first() if tpl_id else None
        base_context = payload.get('context') or {}
    if not tpl:
        return HttpResponseBadRequest('Template not found')
    django_engine = engines['django']
    template = django_engine.from_string(tpl.html_content or '')
    rendered = template.render(base_context)
    return JsonResponse({'rendered_html': rendered})


# Internal helper to perform the snapshot/send actions (re-usable by approval flow)
def _perform_offer_send(o, acting_user=None, request=None):
    """Render, snapshot, create tokens, enqueue email. Returns dict with tokens."""
    # build context
    context = {'candidate_name': o.candidate_name, 'candidate_email': o.candidate_email}
    for fv in o.field_values.all():
        key = fv.field_definition.key if fv.field_definition else None
        if key:
            context[key] = fv.value
    django_engine = engines['django']
    tpl = o.template
    rendered = django_engine.from_string(tpl.html_content or '').render(context) if tpl else ''

    prev_status = o.status
    o.rendered_html = rendered
    o.rendered_email_html = ''
    o.status = 'sent'
    o.sent_at = timezone.now()
    o.save()

    # record status history
    OfferStatusHistory.objects.create(offer=o, from_status=(prev_status or 'draft'), to_status='sent', changed_by=acting_user, timestamp=timezone.now())

    # create tokens
    view_token = OfferSendToken.objects.create(offer=o, token_type='view', expires_at=timezone.now() + timedelta(days=30))
    accept_token = OfferSendToken.objects.create(offer=o, token_type='accept', expires_at=timezone.now() + timedelta(days=30))
    reject_token = OfferSendToken.objects.create(offer=o, token_type='reject', expires_at=timezone.now() + timedelta(days=30))

    # Build absolute URLs if request available
    view_url = accept_url = reject_url = None
    if request is not None:
        from django.urls import reverse
        view_url = request.build_absolute_uri(reverse('public_offer_view', args=[view_token.token]))
        accept_url = request.build_absolute_uri(reverse('public_offer_accept', args=[accept_token.token]))
        reject_url = request.build_absolute_uri(reverse('public_offer_reject', args=[reject_token.token]))

    # Prepare email context
    email_context = {
        'candidate_name': o.candidate_name,
        'candidate_email': o.candidate_email,
        'offer_view_link': view_url,
        'offer_accept_link': accept_url,
        'offer_reject_link': reject_url,
        'offer_html': rendered,
    }

    # Enqueue email send
    try:
        template_key = 'offer_sent'
        # Prefer FK email_template if set on Offer
        if getattr(o, 'email_template', None):
            email_tpl = o.email_template
            subject = django_engine.from_string(email_tpl.subject_template or '').render(email_context)
            body_html = django_engine.from_string(email_tpl.html_body_template or '').render(email_context)
            from ..tasks import send_raw_email_async
            send_raw_email_async.delay(o.candidate_email, subject, body_html)
        else:
            from ..tasks import send_email_async
            send_email_async.delay(o.candidate_email, template_key, email_context)
    except Exception:
        OfferStatusHistory.objects.create(offer=o, from_status='sent', to_status='sent', changed_by=acting_user, comment='Failed to enqueue email send')

    return {'view': view_token.token, 'accept': accept_token.token, 'reject': reject_token.token}


# Email template choices endpoint for frontend
@login_required
@require_http_methods(['GET'])
def offer_email_template_choices(request):
    qs = OfferEmailTemplate.objects.filter(tenant=request.user.tenant) if request.user.tenant else OfferEmailTemplate.objects.all()
    data = [{'id': t.id, 'name': t.name} for t in qs.order_by('name')]
    return JsonResponse({'choices': data})


# Admin analytics endpoint for offers
@login_required
@require_http_methods(['GET'])
def offer_analytics(request):
    # permission check: super_admin or explicit offer permission
    if not (request.user.role == 'super_admin' or request.user.has_perm_key('send_offer') or request.user.has_perm_key('manage_offers') or request.user.has_perm_key('view_offer_analytics')):
        return HttpResponseForbidden('Insufficient permissions')
    qs = Offer.objects.filter(tenant=request.user.tenant) if request.user.tenant else Offer.objects.all()
    total = qs.count()
    sent = qs.filter(status='sent').count()
    accepted = qs.filter(status='accepted').count()
    rejected = qs.filter(status='rejected').count()
    acceptance_rate = (accepted / sent * 100.0) if sent else 0.0
    # avg time to accept in hours
    accepted_qs = qs.filter(status='accepted', sent_at__isnull=False, accepted_at__isnull=False)
    total_seconds = 0
    cnt = 0
    for o in accepted_qs:
        delta = (o.accepted_at - o.sent_at).total_seconds()
        if delta >= 0:
            total_seconds += delta
            cnt += 1
    avg_time_hours = (total_seconds / cnt / 3600.0) if cnt else None
    return JsonResponse({'total': total, 'sent': sent, 'accepted': accepted, 'rejected': rejected, 'acceptance_rate': acceptance_rate, 'avg_time_to_accept_hours': avg_time_hours})


# Export offers CSV for admin
@login_required
@require_http_methods(['GET'])
def export_offers_csv(request):
    if not (request.user.role == 'super_admin' or request.user.has_perm_key('send_offer') or request.user.has_perm_key('manage_offers') or request.user.has_perm_key('export_offer')):
        return HttpResponseForbidden('Insufficient permissions')
    qs = Offer.objects.filter(tenant=request.user.tenant) if request.user.tenant else Offer.objects.all()
    # Optional filters
    status = request.GET.get('status')
    if status:
        qs = qs.filter(status=status)
    import csv
    from io import StringIO
    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(['id', 'candidate_name', 'candidate_email', 'status', 'sent_at', 'accepted_at', 'rejected_at', 'created_at', 'created_by_id'])
    for o in qs.order_by('-created_at'):
        writer.writerow([o.id, o.candidate_name, o.candidate_email, o.status, o.sent_at.isoformat() if o.sent_at else '', o.accepted_at.isoformat() if o.accepted_at else '', o.rejected_at.isoformat() if o.rejected_at else '', o.created_at.isoformat() if o.created_at else '', o.created_by_id if getattr(o, 'created_by_id', None) else ''])
    resp = HttpResponse(out.getvalue(), content_type='text/csv')
    resp['Content-Disposition'] = 'attachment; filename="offers_export.csv"'
    return resp


# Snapshot/render and mark as sent (no email send performed here)
@login_required
@require_http_methods(['POST'])
def offer_snapshot_send(request, offer_id):
    o = get_object_or_404(Offer, id=offer_id)
    if request.user.tenant and o.tenant_id != request.user.tenant.id:
        return HttpResponseForbidden('Not found')
    if not request.user.has_perm_key('send_offer'):
        return HttpResponseForbidden('Insufficient permissions')
    if not o.template:
        return HttpResponseBadRequest('Offer has no template')
    # Approval gating: if there are pending approvals, mark pending and do not send
    if o.approvals.filter(status='pending').exists():
        o.status = 'pending_approval'
        o.save()
        OfferStatusHistory.objects.create(offer=o, from_status='draft', to_status='pending_approval', changed_by=request.user, timestamp=timezone.now())
        return JsonResponse({'offer_id': o.id, 'status': o.status, 'message': 'Offer requires approvals before sending'})

    tokens = _perform_offer_send(o, acting_user=request.user, request=request)
    return JsonResponse({'offer_id': o.id, 'status': o.status, 'view_token': tokens['view'], 'accept_token': tokens['accept'], 'reject_token': tokens['reject']})


# Approvals list/create endpoints
@login_required
@require_http_methods(['GET', 'POST'])
def offer_approvals_list(request, offer_id):
    o = get_object_or_404(Offer, id=offer_id)
    if request.user.tenant and o.tenant_id != request.user.tenant.id:
        return HttpResponseForbidden('Not found')
    if request.method == 'GET':
        data = [
            {
                'id': a.id,
                'approver_id': a.approver_id,
                'order': a.order,
                'status': a.status,
                'comment': a.comment,
                'acted_at': a.acted_at.isoformat() if a.acted_at else None,
            }
            for a in o.approvals.all().order_by('order')
        ]
        return JsonResponse({'approvals': data})
    # POST - create approval entries
    if not request.user.has_perm_key('approve_offer'):
        return HttpResponseForbidden('Insufficient permissions')
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return HttpResponseBadRequest('Invalid JSON payload')
    approver_id = payload.get('approver_id')
    order = int(payload.get('order') or 0)
    approver = None
    if approver_id:
        from ..models import User
        approver = User.objects.filter(id=approver_id).first()
    ap = OfferApproval.objects.create(offer=o, approver=approver, order=order, status='pending')
    return JsonResponse({'approval': {'id': ap.id, 'approver_id': ap.approver_id, 'order': ap.order, 'status': ap.status}}, status=201)


@login_required
@require_http_methods(['GET', 'PUT', 'PATCH', 'DELETE'])
def offer_approval_detail(request, offer_id, approval_id):
    o = get_object_or_404(Offer, id=offer_id)
    approval = get_object_or_404(OfferApproval, id=approval_id, offer=o)
    if request.user.tenant and o.tenant_id != request.user.tenant.id:
        return HttpResponseForbidden('Not found')
    if request.method == 'GET':
        return JsonResponse({'approval': {'id': approval.id, 'approver_id': approval.approver_id, 'order': approval.order, 'status': approval.status, 'comment': approval.comment}})
    if request.method in ('PUT', 'PATCH'):
        if not request.user.has_perm_key('approve_offer'):
            return HttpResponseForbidden('Insufficient permissions')
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return HttpResponseBadRequest('Invalid JSON payload')
        changed = False
        if 'approver_id' in payload:
            from ..models import User
            approval.approver = User.objects.filter(id=payload.get('approver_id')).first()
            changed = True
        if 'order' in payload:
            approval.order = int(payload.get('order') or 0)
            changed = True
        if 'status' in payload:
            approval.status = payload.get('status')
            changed = True
        if 'comment' in payload:
            approval.comment = payload.get('comment')
            changed = True
        if changed:
            approval.save()
        return JsonResponse({'approval': {'id': approval.id, 'approver_id': approval.approver_id, 'order': approval.order, 'status': approval.status}})
    if request.method == 'DELETE':
        if not request.user.has_perm_key('approve_offer'):
            return HttpResponseForbidden('Insufficient permissions')
        approval.delete()
        return JsonResponse({'deleted': True})


# Approver actions: approve or reject a specific OfferApproval
@login_required
@require_http_methods(['POST'])
def approve_offer_approval(request, offer_id, approval_id):
    o = get_object_or_404(Offer, id=offer_id)
    approval = get_object_or_404(OfferApproval, id=approval_id, offer=o)
    if request.user.tenant and o.tenant_id != request.user.tenant.id:
        return HttpResponseForbidden('Not found')
    # Permission: approver must be the assigned approver or have approve_offer permission
    if not (request.user.has_perm_key('approve_offer') or (approval.approver and approval.approver_id == request.user.id)):
        return HttpResponseForbidden('Insufficient permissions')
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        payload = {}
    approval.status = 'approved'
    approval.comment = payload.get('comment', '')
    approval.acted_at = timezone.now()
    approval.save()
    OfferStatusHistory.objects.create(offer=o, from_status=o.status, to_status=o.status, changed_by=request.user, comment=f'Approval {approval.id} approved')
    # If all approvals are approved, and offer is pending_approval or draft, auto-send
    if not o.approvals.filter(status='pending').exists() and not o.approvals.filter(status='rejected').exists():
        if o.status in ('draft', 'pending_approval'):
            tokens = _perform_offer_send(o, acting_user=request.user, request=request)
            return JsonResponse({'offer_id': o.id, 'status': o.status, 'sent': True, 'view_token': tokens['view'], 'accept_token': tokens['accept'], 'reject_token': tokens['reject']})
    return JsonResponse({'offer_id': o.id, 'status': o.status, 'approved': True})


@login_required
@require_http_methods(['POST'])
def reject_offer_approval(request, offer_id, approval_id):
    o = get_object_or_404(Offer, id=offer_id)
    approval = get_object_or_404(OfferApproval, id=approval_id, offer=o)
    if request.user.tenant and o.tenant_id != request.user.tenant.id:
        return HttpResponseForbidden('Not found')
    if not (request.user.has_perm_key('approve_offer') or (approval.approver and approval.approver_id == request.user.id)):
        return HttpResponseForbidden('Insufficient permissions')
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        reason = payload.get('reason', '')
    except Exception:
        reason = ''
    approval.status = 'rejected'
    approval.comment = reason
    approval.acted_at = timezone.now()
    approval.save()
    # mark offer rejected
    prev = o.status
    o.status = 'rejected'
    o.rejected_at = timezone.now()
    OfferStatusHistory.objects.create(offer=o, from_status=prev, to_status='rejected', changed_by=request.user, reason=reason)
    return JsonResponse({'offer_id': o.id, 'status': o.status, 'rejected': True})


@login_required
@require_http_methods(['GET'])
def offer_pdf_export_api_view(request, offer_id):
    """Download offer document as high-fidelity PDF."""
    from ..services.pdf_service import generate_offer_pdf_response
    o = get_object_or_404(Offer, id=offer_id)
    if request.user.tenant and o.tenant_id != request.user.tenant.id:
        return HttpResponseForbidden('Not found')
    return generate_offer_pdf_response(o)

