"""
E-Signature views for document signing workflow.

Handles signature creation, validation, and document signature management.
Signatures and signature fields are now stored in OnboardingDocument.meta as JSON.
"""
import json
import base64
import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from ..models import OnboardingDocument
from ..decorators import permission_required

SIGNATURE_TYPES = [
    ('digital_pad', 'Digital Pad'),
    ('typed', 'Typed Name'),
    ('upload', 'Uploaded Image'),
]


@login_required
def document_sign_page(request, doc_id):
    """Display document signing page with signature pad."""
    doc = get_object_or_404(OnboardingDocument, id=doc_id)

    if doc.employee and doc.employee != request.user:
        if not request.user.has_perm_key('manage_employee_documents'):
            return render(request, '403.html', status=403)

    sig_fields = doc.meta.get('signature_fields', [])

    ctx = {
        'document': doc,
        'sig_fields': sig_fields,
        'signature_types': SIGNATURE_TYPES,
    }

    return render(request, 'signatures/sign_document.html', ctx)


@login_required
@require_http_methods(['POST'])
def create_signature(request):
    """Create a new signature from the signing widget."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    doc_id = data.get('document_id')
    if not doc_id:
        return JsonResponse({'error': 'document_id required'}, status=400)

    doc = get_object_or_404(OnboardingDocument, id=doc_id)

    if doc.employee and doc.employee != request.user:
        if not request.user.has_perm_key('manage_employee_documents'):
            return JsonResponse({'error': 'Permission denied'}, status=403)

    sig_image = data.get('signature_image', '').strip()
    if not sig_image or len(sig_image) < 50:
        return JsonResponse({'error': 'Signature image too small'}, status=400)

    sig_id = str(uuid.uuid4())
    signature_record = {
        'id': sig_id,
        'user_id': request.user.id,
        'user_email': request.user.email,
        'signature_image': sig_image,
        'signature_type': data.get('signature_type', 'digital_pad'),
        'signer_name': data.get('signer_name', request.user.full_name),
        'signer_title': data.get('signer_title', ''),
        'ip_address': get_client_ip(request),
        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
        'signed_at': timezone.now().isoformat(),
        'consent_checked': data.get('consent_checked', False),
    }

    if not doc.meta:
        doc.meta = {}
    if 'signatures' not in doc.meta:
        doc.meta['signatures'] = []

    doc.meta['signatures'].append(signature_record)

    sig_field_id = data.get('signature_field_id')
    if sig_field_id and 'signature_fields' in doc.meta:
        for field in doc.meta['signature_fields']:
            if field.get('id') == sig_field_id:
                field['signed'] = True
                field['signature_id'] = sig_id
                break

    all_fields = doc.meta.get('signature_fields', [])
    required_fields = [f for f in all_fields if not f.get('optional', False)]
    all_signed = all(f.get('signed', False) for f in required_fields) and len(required_fields) > 0

    if all_signed:
        doc.is_signed = True
        doc.signed_at = timezone.now()

    doc.save()

    return JsonResponse({
        'success': True,
        'signature_id': sig_id,
        'all_signed': all_signed,
    })


@login_required
@require_http_methods(['POST'])
def verify_signature(request, sig_id):
    """Verify a signature by a witness or approver."""
    if not request.user.has_perm_key('manage_employee_documents'):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    doc_id = request.POST.get('document_id')
    if not doc_id:
        return JsonResponse({'error': 'document_id required'}, status=400)

    doc = get_object_or_404(OnboardingDocument, id=doc_id)

    signatures = doc.meta.get('signatures', [])
    for sig in signatures:
        if sig.get('id') == sig_id:
            sig['witness_user_id'] = request.user.id
            sig['witness_signed_at'] = timezone.now().isoformat()
            sig['witness_notes'] = request.POST.get('notes', '')
            doc.save()
            return JsonResponse({
                'success': True,
                'verified_by': request.user.full_name,
                'verified_at': sig['witness_signed_at'],
            })

    return JsonResponse({'error': 'Signature not found'}, status=404)


@login_required
def view_signature(request, sig_id):
    """View a signature record with validation status."""
    doc_id = request.GET.get('document_id')
    if not doc_id:
        return JsonResponse({'error': 'document_id required'}, status=400)

    doc = get_object_or_404(OnboardingDocument, id=doc_id)

    if doc.employee and doc.employee != request.user:
        if not request.user.has_perm_key('view_employee_data'):
            return render(request, '403.html', status=403)

    signatures = doc.meta.get('signatures', [])
    signature = next((s for s in signatures if s.get('id') == sig_id), None)

    if not signature:
        return JsonResponse({'error': 'Signature not found'}, status=404)

    ctx = {
        'signature': signature,
        'signature_display': signature.get('signature_image'),
    }

    return render(request, 'signatures/view_signature.html', ctx)


@login_required
def download_signature(request, sig_id):
    """Download signature as PNG."""
    doc_id = request.GET.get('document_id')
    if not doc_id:
        return JsonResponse({'error': 'document_id required'}, status=400)

    doc = get_object_or_404(OnboardingDocument, id=doc_id)

    if doc.employee and doc.employee != request.user:
        if not request.user.has_perm_key('manage_employee_documents'):
            return render(request, '403.html', status=403)

    signatures = doc.meta.get('signatures', [])
    signature = next((s for s in signatures if s.get('id') == sig_id), None)

    if not signature:
        return JsonResponse({'error': 'Signature not found'}, status=404)

    sig_image = signature.get('signature_image', '')
    if sig_image.startswith('data:'):
        _, data_part = sig_image.split(',', 1)
    else:
        data_part = sig_image

    try:
        image_data = base64.b64decode(data_part)
    except Exception:
        return JsonResponse({'error': 'Invalid signature data'}, status=400)

    from django.http import HttpResponse
    response = HttpResponse(image_data, content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="signature_{sig_id}.png"'
    return response


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
