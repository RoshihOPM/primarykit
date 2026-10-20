"""Bind a Deal to its owner-private Kanban projection safely."""

from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, ValidationError

from apps.deals.models import Deal
from apps.kanban.models import Board, Card, Column

from .models import DealCardLink


class DuplicateLink(ValidationError):
    status_code = 409
    default_detail = "Deal or card is already linked."


@transaction.atomic
def bind_deal_card(*, actor, deal_id, card_id):
    deal = Deal.objects.select_for_update().filter(pk=deal_id, owner=actor).first()
    if deal is None:
        raise NotFound()
    card = Card.objects.filter(pk=card_id, board__owner=actor).first()
    if card is None:
        raise NotFound()
    board = Board.objects.select_for_update().filter(pk=card.board_id, owner=actor).first()
    if board is None:
        raise NotFound()
    card = Card.objects.select_for_update().select_related("column").get(pk=card.pk, board=board)
    # Column identity is explicit and unambiguous, not a user-supplied generic ID.
    for stage in Deal.Stage.values:
        if Column.objects.filter(board=board, name__iexact=stage).count() != 1:
            raise ValidationError({"board": "Exactly one column per Deal stage is required."})
    if card.column.name.casefold() != deal.stage:
        raise ValidationError({"card": "Card column must match the authoritative Deal stage."})
    try:
        with transaction.atomic():
            return DealCardLink.objects.create(owner=actor, deal=deal, card=card)
    except IntegrityError as exc:
        raise DuplicateLink() from exc
