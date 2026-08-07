import json
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.cache import cache

from ..models_offers import OfferSendToken, Offer, OfferStatusHistory, OfferSignature
from ..services import notify, log_activity


@require_http_methods(["GET"])
def public_offer_view(request, token):
    tok = OfferSendToken.objects.filter(token=token).select_related('offer').first()
    if not tok:
        return HttpResponseForbidden('Invalid token')

    # Rate-limit views per IP + token
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR', 'unknown')
    rl_key = f'offer_view_rl:{token}:{ip}'
    count = cache.get(rl_key, 0)
    if count >= 100:
        return HttpResponse(status=429, content='Too many requests')
    cache.set(rl_key, count + 1, timeout=3600)

    if tok.expires_at and tok.expires_at < timezone.now():
        return HttpResponseForbidden('Token expired')

    offer = tok.offer
    accept_tok = OfferSendToken.objects.filter(offer=offer, token_type='accept').first()
    reject_tok = OfferSendToken.objects.filter(offer=offer, token_type='reject').first()

    accept_token_str = accept_tok.token if accept_tok else ''
    reject_token_str = reject_tok.token if reject_tok else ''

    html_body = offer.rendered_html or offer.rendered_email_html or '<p>Offer content unavailable.</p>'
    
    # Check signature status
    signature = offer.signatures.first()

    status_badge_html = f'<span class="badge bg-primary fs-6 px-3 py-2">{offer.status.upper()}</span>'
    if offer.status == 'accepted':
        status_badge_html = '<span class="badge bg-success fs-6 px-3 py-2"><i class="bi bi-check-circle me-1"></i> ACCEPTED & SIGNED</span>'
    elif offer.status == 'rejected':
        status_badge_html = '<span class="badge bg-danger fs-6 px-3 py-2"><i class="bi bi-x-circle me-1"></i> REJECTED</span>'
    elif offer.status == 'expired':
        status_badge_html = '<span class="badge bg-secondary fs-6 px-3 py-2"><i class="bi bi-clock me-1"></i> EXPIRED</span>'

    page = f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Employment Offer - {offer.candidate_name}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        body {{ background-color: #f8fafc; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; color: #334155; }}
        .paper-container {{ max-width: 900px; margin: 30px auto; background: #ffffff; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.06); overflow: hidden; }}
        .paper-header {{ background: linear-gradient(135deg, #1e293b, #0f172a); color: #ffffff; padding: 28px 36px; }}
        .paper-body {{ padding: 40px 48px; min-height: 500px; line-height: 1.7; }}
        .paper-footer {{ background: #f1f5f9; border-top: 1px solid #e2e8f0; padding: 24px 36px; }}
        .signature-canvas-wrap {{ border: 2px dashed #cbd5e1; border-radius: 8px; background: #ffffff; position: relative; cursor: crosshair; }}
        #sigCanvas {{ width: 100%; height: 160px; touch-action: none; }}
    </style>
</head>
<body>
    <div class="container py-4">
        <div class="paper-container">
            <div class="paper-header d-flex justify-content-between align-items-center">
                <div>
                    <h3 class="mb-1 fw-bold text-white"><i class="bi bi-file-earmark-check me-2 text-primary"></i>Employment Offer Document</h3>
                    <p class="mb-0 text-slate-300 small">Offer ID: {offer.offer_number} | Prepared for {offer.candidate_name}</p>
                </div>
                <div>{status_badge_html}</div>
            </div>

            <div class="paper-body">
                {html_body}

                {'<div class="alert alert-success mt-4 p-3 rounded-3"><i class="bi bi-shield-check me-2 fs-5"></i>This offer was digitally signed by <strong>' + signature.signer_name + '</strong> on ' + signature.signed_at.strftime("%B %d, %Y at %H:%M UTC") + '.</div>' if signature else ''}
            </div>

            <div class="paper-footer">
                {'<div class="d-flex justify-content-between align-items-center"><div class="text-muted small"><i class="bi bi-shield-lock me-1"></i> Secure single-use token verification</div><div><a href="/api/offers/' + str(offer.id) + '/pdf/" class="btn btn-outline-primary"><i class="bi bi-download me-1"></i> Download Signed PDF</a></div></div>' if offer.status == 'accepted' else ''}

                {'<div class="d-flex justify-content-between align-items-center gap-3"><div><p class="mb-0 fw-semibold text-dark">Please review this document carefully before making a decision.</p><small class="text-muted">Accepting this offer records your e-signature and IP address for validation.</small></div><div class="d-flex gap-2"><button type="button" class="btn btn-danger px-4" data-bs-toggle="modal" data-bs-target="#rejectModal"><i class="bi bi-x-circle me-1"></i> Decline Offer</button><button type="button" class="btn btn-success px-4 fw-semibold" data-bs-toggle="modal" data-bs-target="#acceptModal"><i class="bi bi-pen me-1"></i> Accept & Sign Offer</button></div></div>' if offer.status == 'sent' else ''}
            </div>
        </div>
    </div>

    <!-- Accept & E-Sign Modal -->
    <div class="modal fade" id="acceptModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content border-0">
                <div class="modal-header bg-success text-white">
                    <h5 class="modal-title"><i class="bi bi-pen me-2"></i>E-Sign & Accept Employment Offer</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body p-4">
                    <ul class="nav nav-pills nav-fill mb-3" id="sigTypeTab">
                        <li class="nav-item">
                            <button class="nav-link active" id="draw-tab" data-bs-toggle="tab" data-bs-target="#draw-pane">Draw Signature</button>
                        </li>
                        <li class="nav-item">
                            <button class="nav-link" id="type-tab" data-bs-toggle="tab" data-bs-target="#type-pane">Typed Signature</button>
                        </li>
                    </ul>

                    <div class="tab-content pt-2">
                        <!-- Draw Signature Pane -->
                        <div class="tab-pane fade show active" id="draw-pane">
                            <label class="form-label fw-semibold">Draw your signature in the box below:</label>
                            <div class="signature-canvas-wrap mb-2">
                                <canvas id="sigCanvas"></canvas>
                            </div>
                            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="clearCanvas()"><i class="bi bi-eraser me-1"></i>Clear Pad</button>
                        </div>

                        <!-- Typed Signature Pane -->
                        <div class="tab-pane fade" id="type-pane">
                            <label class="form-label fw-semibold">Full Legal Name</label>
                            <input type="text" id="typedNameInput" class="form-control form-control-lg" value="{offer.candidate_name}">
                            <small class="text-muted">By typing your name, you intend to execute this offer agreement electronically.</small>
                        </div>
                    </div>

                    <div class="mt-4 pt-3 border-top">
                        <div class="form-check">
                            <input class="form-check-input" type="checkbox" id="consentCheck" required>
                            <label class="form-check-label text-muted small" for="consentCheck">
                                I agree to sign this employment offer document electronically and acknowledge that my electronic signature has the same legal force and effect as a handwritten signature.
                            </label>
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-light" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-success px-4" onclick="submitAccept()"><i class="bi bi-check-circle me-1"></i> Submit E-Signature</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Reject Modal -->
    <div class="modal fade" id="rejectModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content border-0">
                <div class="modal-header bg-danger text-white">
                    <h5 class="modal-title"><i class="bi bi-x-circle me-2"></i>Decline Employment Offer</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body p-4">
                    <label class="form-label fw-semibold">Reason for declining (optional)</label>
                    <textarea id="rejectReason" class="form-control" rows="4" placeholder="Please let us know your feedback or reasons for declining..."></textarea>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-light" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-danger" onclick="submitReject()">Decline Offer</button>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        var acceptToken = "{accept_token_str}";
        var rejectToken = "{reject_token_str}";

        var canvas = document.getElementById('sigCanvas');
        var ctx = canvas ? canvas.getContext('2d') : null;
        var drawing = false;

        if (canvas) {{
            function resizeCanvas() {{
                canvas.width = canvas.parentElement.clientWidth;
                canvas.height = 160;
                ctx.lineWidth = 2.5;
                ctx.lineCap = 'round';
                ctx.strokeStyle = '#0f172a';
            }}
            window.addEventListener('resize', resizeCanvas);
            setTimeout(resizeCanvas, 300);

            canvas.addEventListener('mousedown', function(e) {{ drawing = true; ctx.beginPath(); ctx.moveTo(e.offsetX, e.offsetY); }});
            canvas.addEventListener('mousemove', function(e) {{ if (drawing) {{ ctx.lineTo(e.offsetX, e.offsetY); ctx.stroke(); }} }});
            window.addEventListener('mouseup', function() {{ drawing = false; }});

            canvas.addEventListener('touchstart', function(e) {{
                drawing = true;
                var rect = canvas.getBoundingClientRect();
                var touch = e.touches[0];
                ctx.beginPath();
                ctx.moveTo(touch.clientX - rect.left, touch.clientY - rect.top);
                e.preventDefault();
            }});
            canvas.addEventListener('touchmove', function(e) {{
                if (drawing) {{
                    var rect = canvas.getBoundingClientRect();
                    var touch = e.touches[0];
                    ctx.lineTo(touch.clientX - rect.left, touch.clientY - rect.top);
                    ctx.stroke();
                    e.preventDefault();
                }}
            }});
            window.addEventListener('touchend', function() {{ drawing = false; }});
        }}

        function clearCanvas() {{
            if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
        }}

        function submitAccept() {{
            if (!document.getElementById('consentCheck').checked) {{
                alert('Please check the consent checkbox to agree to electronic signature terms.');
                return;
            }}

            var activeTab = document.querySelector('#sigTypeTab .active').id;
            var payload = {{}};
            if (activeTab === 'draw-tab') {{
                payload.signature_method = 'drawn';
                payload.signature_blob = canvas.toDataURL('image/png');
                payload.signer_name = "{offer.candidate_name}";
            }} else {{
                payload.signature_method = 'typed';
                payload.signer_name = document.getElementById('typedNameInput').value || "{offer.candidate_name}";
            }}

            fetch('/offers/' + acceptToken + '/accept/', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(payload)
            }})
            .then(function(res) {{ return res.json(); }})
            .then(function(data) {{
                if (data.status === 'accepted') {{
                    alert('Thank you! Your offer has been successfully accepted and signed.');
                    window.location.reload();
                }} else {{
                    alert(data.error || 'Failed to submit signature.');
                }}
            }})
            .catch(function(err) {{
                alert('Error submitting offer acceptance.');
            }});
        }}

        function submitReject() {{
            var reason = document.getElementById('rejectReason').value;
            fetch('/offers/' + rejectToken + '/reject/', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ reason: reason }})
            }})
            .then(function(res) {{ return res.json(); }})
            .then(function(data) {{
                if (data.status === 'rejected') {{
                    alert('Offer status updated to declined.');
                    window.location.reload();
                }} else {{
                    alert(data.error || 'Failed to decline offer.');
                }}
            }})
            .catch(function(err) {{
                alert('Error declining offer.');
            }});
        }}
    </script>
</body>
</html>"""
    log_activity(request=request, user=None, action='offer_viewed_public', entity_type='offer', entity_id=offer.id, description=f'Viewed by token {tok.token_type} from {ip}')
    return HttpResponse(page)


@csrf_exempt
@require_http_methods(["POST"])
def public_offer_accept(request, token):
    tok = OfferSendToken.objects.filter(token=token, token_type='accept').select_related('offer').first()
    if not tok:
        return HttpResponseForbidden('Invalid token')
    if tok.used:
        return HttpResponseForbidden('Token already used')
    if tok.expires_at and tok.expires_at < timezone.now():
        return HttpResponseForbidden('Token expired')
    offer = tok.offer
    if offer.status != 'sent':
        return HttpResponseBadRequest('Offer is not in a state that can be accepted')

    ip_addr = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR', '')
    signer_name = offer.candidate_name
    signature_method = 'typed'
    signature_blob = ''

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        signer_name = payload.get('signer_name') or offer.candidate_name
        signature_method = payload.get('signature_method') or 'typed'
        signature_blob = payload.get('signature_blob') or ''
    except Exception:
        pass

    sig = OfferSignature.objects.create(
        offer=offer,
        signer_name=signer_name,
        signature_method=signature_method,
        signature_blob=signature_blob,
        signed_at=timezone.now(),
        ip_address=ip_addr
    )

    offer.status = 'accepted'
    offer.accepted_at = timezone.now()

    # Append official signature audit trail to rendered HTML
    sig_img_html = f'<img src="{signature_blob}" style="max-height: 80px;" alt="Signature">' if signature_blob and signature_method == 'drawn' else f'<span style="font-family: cursive; font-size: 1.5rem;">{signer_name}</span>'
    audit_block = f"""
    <div style="margin-top: 40px; padding: 20px; border: 1px solid #cbd5e1; border-radius: 8px; background-color: #f8fafc;">
        <h4 style="margin-top: 0; color: #1e293b;">Accepted & Digitally Signed</h4>
        <p><strong>Signer Name:</strong> {signer_name}</p>
        <p><strong>Signature:</strong></p>
        <div style="margin-bottom: 10px;">{sig_img_html}</div>
        <p style="font-size: 0.85rem; color: #64748b; margin-bottom: 0;">
            Signed on {sig.signed_at.strftime("%B %d, %Y at %H:%M:%S UTC")} | IP Address: {ip_addr}
        </p>
    </div>
    """
    offer.rendered_html = (offer.rendered_html or '') + audit_block
    offer.save()

    tok.used = True
    tok.save()

    OfferStatusHistory.objects.create(offer=offer, from_status='sent', to_status='accepted', changed_by=None, timestamp=timezone.now())

    if offer.created_by:
        notify(offer.created_by, f'Offer accepted: {offer.candidate_name}', message=f'The offer to {offer.candidate_name} was accepted.', link=f'/admin/offers/{offer.id}/')

    log_activity(request=request, user=None, action='offer_accepted_public', entity_type='offer', entity_id=offer.id, description=f'Accepted by {signer_name} ({signature_method})')
    return JsonResponse({'offer_id': offer.id, 'status': offer.status})


@csrf_exempt
@require_http_methods(["POST"])
def public_offer_reject(request, token):
    tok = OfferSendToken.objects.filter(token=token, token_type='reject').select_related('offer').first()
    if not tok:
        return HttpResponseForbidden('Invalid token')
    if tok.used:
        return HttpResponseForbidden('Token already used')
    if tok.expires_at and tok.expires_at < timezone.now():
        return HttpResponseForbidden('Token expired')
    offer = tok.offer
    if offer.status != 'sent':
        return HttpResponseBadRequest('Offer is not in a state that can be rejected')

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        reason = payload.get('reason', '')
    except Exception:
        reason = ''

    offer.status = 'rejected'
    offer.rejected_at = timezone.now()
    offer.save()

    tok.used = True
    tok.save()

    OfferStatusHistory.objects.create(offer=offer, from_status='sent', to_status='rejected', changed_by=None, reason=reason, timestamp=timezone.now())

    if offer.created_by:
        notify(offer.created_by, f'Offer rejected: {offer.candidate_name}', message=f'The offer to {offer.candidate_name} was rejected. Reason: {reason}', link=f'/admin/offers/{offer.id}/')

    log_activity(request=request, user=None, action='offer_rejected_public', entity_type='offer', entity_id=offer.id, description=f'Rejected. Reason: {reason}')
    return JsonResponse({'offer_id': offer.id, 'status': offer.status})
