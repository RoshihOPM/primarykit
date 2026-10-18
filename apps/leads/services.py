"""Independent Leads lifecycle and optimistic edits."""

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
def edit_lead(*, actor, lead_id, expected_version, changes):
    lead = Lead.objects.select_for_update().filter(pk=lead_id, owner=actor).first()
    if lead is None:
        raise NotFound()
    if lead.version != expected_version:
        raise StaleLead()
    allowed = {"title", "contact_name", "contact_email", "contact_phone", "source", "notes"}
    if not changes or not set(changes) <= allowed:
        raise ValidationError("Invalid or empty lead changes.")
    for key, value in changes.items():
        setattr(lead, key, value)
    lead.version += 1
    lead.save(update_fields=(*changes.keys(), "version", "updated_at"))
    return lead


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
