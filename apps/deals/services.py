"""Versioned owner-private deal edits and explicit stage transitions."""

from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from .models import Deal

STAGES = {
    Deal.Stage.OPEN: {Deal.Stage.NEGOTIATION, Deal.Stage.LOST},
    Deal.Stage.NEGOTIATION: {Deal.Stage.WON, Deal.Stage.LOST},
    Deal.Stage.WON: set(),
    Deal.Stage.LOST: set(),
}


class StaleDeal(ValidationError):
    status_code = 409
    default_detail = "Deal has changed; refresh and retry."


def _locked_deal(actor, deal_id):
    deal = Deal.objects.select_for_update().filter(pk=deal_id, owner=actor).first()
    if deal is None:
        raise NotFound()
    return deal


@transaction.atomic
def edit_deal(*, actor, deal_id, expected_version, changes):
    deal = _locked_deal(actor, deal_id)
    if deal.version != expected_version:
        raise StaleDeal()
    if not changes or not set(changes) <= {"title", "amount_minor", "currency", "notes"}:
        raise ValidationError("Invalid or empty changes.")
    for key, value in changes.items():
        setattr(deal, key, value)
    deal.version += 1
    deal.save(update_fields=(*changes.keys(), "version", "updated_at"))
    return deal


@transaction.atomic
def transition_deal(*, actor, deal_id, expected_version, stage):
    deal = _locked_deal(actor, deal_id)
    if deal.version != expected_version:
        raise StaleDeal()
    if stage not in STAGES[deal.stage]:
        raise ValidationError({"stage": "Invalid stage transition."})
    deal.stage = stage
    deal.version += 1
    deal.save(update_fields=("stage", "version", "updated_at"))
    return deal
