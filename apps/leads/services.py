"""Independent Leads lifecycle and optimistic edits."""

from django.apps import apps
from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.audit import record_audit_event

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


def validate_assignee(*, actor, assignee):
    """Only an active self or a member of the same active organization may be assigned.

    Assignment NEVER grants read/write access; ownership remains authoritative.
    """
    if assignee is None:
        return
    if not assignee.is_active:
        raise ValidationError({"assigned_to": "Invalid assignee."})
    if actor.pk == assignee.pk:
        return
    if not apps.is_installed("apps.organizations"):
        raise ValidationError({"assigned_to": "Invalid assignee."})
    Membership = apps.get_model("organizations", "Membership")
    common = Membership.objects.filter(
        user=actor, is_active=True, organization__is_active=True
    ).values("organization_id")
    if not Membership.objects.filter(
        user=assignee, is_active=True, organization_id__in=common
    ).exists():
        raise ValidationError({"assigned_to": "Invalid assignee."})


@transaction.atomic
def create_lead(*, actor, data):
    validate_assignee(actor=actor, assignee=data.get("assigned_to"))
    lead = Lead.objects.create(owner=actor, **data)
    record_audit_event(
        actor=actor,
        action="leads.created",
        target_type="leads.Lead",
        target_id=lead.pk,
    )
    return lead


@transaction.atomic
def edit_lead(*, actor, lead_id, expected_version, changes):
    lead = Lead.objects.select_for_update().filter(pk=lead_id, owner=actor).first()
    if lead is None:
        raise NotFound()
    if lead.version != expected_version:
        raise StaleLead()
    allowed = {
        "title",
        "contact_name",
        "contact_email",
        "contact_phone",
        "source",
        "notes",
        "assigned_to",
    }
    if not changes or not set(changes) <= allowed:
        raise ValidationError("Invalid or empty lead changes.")
    if "assigned_to" in changes:
        validate_assignee(actor=actor, assignee=changes["assigned_to"])
    for key, value in changes.items():
        setattr(lead, key, value)
    lead.version += 1
    lead.save(update_fields=(*changes.keys(), "version", "updated_at"))
    record_audit_event(
        actor=actor,
        action="leads.updated",
        target_type="leads.Lead",
        target_id=lead.pk,
        changes={"fields": sorted(changes)},
    )
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
    record_audit_event(
        actor=actor,
        action="leads.transitioned",
        target_type="leads.Lead",
        target_id=lead.pk,
        changes={"status": status},
    )
    return lead
