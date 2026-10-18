"""Business state transitions with owner scoping and optimistic conflicts."""

from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from .models import Lead

TRANSITIONS = {
    Lead.Status.NEW: {Lead.Status.QUALIFIED, Lead.Status.LOST},
    Lead.Status.QUALIFIED: {Lead.Status.WON, Lead.Status.LOST},
    Lead.Status.WON: set(),
    Lead.Status.LOST: set(),
}


class StaleLead(ValidationError):
    status_code = 409
    default_detail = "Lead has changed; refresh and retry."


@transaction.atomic
def transition_lead(*, actor, lead_id, expected_version, status):
    lead = Lead.objects.select_for_update().filter(pk=lead_id, owner=actor).first()
    if lead is None:
        raise NotFound()
    if lead.version != expected_version:
        raise StaleLead()
    if status not in TRANSITIONS[lead.status]:
        raise ValidationError({"status": "Invalid lifecycle transition."})
    lead.status = status
    lead.version += 1
    lead.save(update_fields=("status", "version", "updated_at"))
    return lead
