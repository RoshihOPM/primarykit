"""Synchronous Django signal receivers run inside the Deal transaction.

Exceptions intentionally propagate: a failed Kanban projection rolls back the
authoritative Deal stage. No external delivery or on_commit side effect occurs.
"""

from rest_framework.exceptions import ValidationError

from apps.kanban.models import Column
from apps.kanban.services import move_card

from .models import DealCardLink


def project_deal_stage(sender, *, actor, deal, previous_stage, **kwargs):
    link = DealCardLink.objects.select_related("card").filter(owner=actor, deal=deal).first()
    if link is None:
        return
    columns = list(Column.objects.filter(board_id=link.card.board_id, name__iexact=deal.stage)[:2])
    if len(columns) != 1:
        raise ValidationError({"stage": "Projection column is missing or ambiguous."})
    move_card(
        actor=actor,
        card_id=link.card_id,
        target_column_id=columns[0].pk,
        expected_version=link.card.version,
    )


def guard_mapped_card_move(sender, *, actor, card, target_column, **kwargs):
    link = DealCardLink.objects.select_related("deal").filter(owner=actor, card=card).first()
    if link is not None and target_column.name.casefold() != link.deal.stage:
        raise ValidationError(
            {"target_column_id": "This card projects a Deal stage; transition the Deal."}
        )
