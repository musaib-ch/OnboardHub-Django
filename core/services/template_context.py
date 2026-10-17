from django.utils import timezone

from ..models_offers import OfferFieldDefinition, SYSTEM_OFFER_PLACEHOLDER_KEYS


def tenant_template_context(tenant):
    context = {}
    if tenant:
        fields = OfferFieldDefinition.objects.filter(tenant=tenant).exclude(
            key__in=SYSTEM_OFFER_PLACEHOLDER_KEYS
        )
        for field in fields:
            meta = field.meta if isinstance(field.meta, dict) else {}
            context[field.key] = meta.get("default_value", "")

    context.update({
        "company_name": tenant.name if tenant else "",
        "company": tenant.name if tenant else "",
        "current_date": timezone.localdate().strftime("%B %d, %Y").replace(" 0", " "),
    })
    return context


def offer_template_context(offer):
    context = tenant_template_context(offer.tenant)
    context.update(offer.offer_data)
    for field_value in offer.field_values.select_related("field_definition"):
        if field_value.field_definition:
            context[field_value.field_definition.key] = field_value.value
    context.update({
        "candidate_name": offer.candidate_name,
        "candidate_email": offer.candidate_email,
        "offer_number": offer.offer_number,
        "company_name": offer.tenant.name if offer.tenant_id else "",
    })
    return context