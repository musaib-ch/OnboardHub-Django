from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from ..decorators import login_required
from ..models_offers import Offer, OfferSignature, OfferStatusHistory
from ..services import log_activity


@login_required
def my_offers(request):
    offers = Offer.objects.filter(candidate_user=request.user).order_by("-created_at")
    for offer in offers.filter(status="sent"):
        expiry = offer.expiry_date
        if expiry and expiry < timezone.now():
            offer.status = "expired"
            offer.save(update_fields=["status", "updated_at"])
    return render(request, "employee/offers.html", {"offers": offers})


@login_required
@require_http_methods(["POST"])
def respond_to_offer(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id, candidate_user=request.user)
    expiry = offer.expiry_date
    if offer.status not in ("sent", "viewed") or (expiry and expiry < timezone.now()):
        messages.error(request, "This offer can no longer be responded to.")
        return redirect("my_offers")
    action = request.POST.get("action")
    if action == "accept":
        OfferSignature.objects.create(
            offer=offer,
            signer_name=request.user.full_name or request.user.email,
            signature_method="typed",
        )
        offer.status = "accepted"
        offer.accepted_at = timezone.now()
        offer.signed_at = offer.accepted_at
        offer.metadata = dict(offer.metadata or {})
        offer.metadata["signed_by_name"] = request.user.full_name or request.user.email
        messages.success(request, "You accepted the offer. Welcome aboard!")
    elif action == "reject":
        offer.status = "rejected"
        offer.rejected_at = timezone.now()
        offer.metadata = dict(offer.metadata or {})
        offer.metadata["rejection_reason"] = (request.POST.get("reason") or "").strip()
        messages.info(request, "Your response has been shared with the hiring team.")
    else:
        messages.error(request, "Choose accept or decline.")
        return redirect("my_offers")
    offer.save()
    OfferStatusHistory.objects.create(
        offer=offer,
        from_status=("sent" if offer.status in ("accepted", "rejected") else offer.status),
        to_status=offer.status,
        changed_by=request.user,
        comment=f"Candidate {action}ed the offer",
    )
    log_activity(request, action=f"offer_{action}ed", entity_type="offer", entity_id=offer.id, description=f"{request.user.email} {action}ed {offer.offer_number}")
    return redirect("my_offers")
