"""Transactional owner-scoped Kanban operations; no implicit CRM state writes."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction

from .models import Board, Card, CardMove, Column


@transaction.atomic
def move_card(*, actor, card_id, target_column_id, expected_version):
    """Move a card with optimistic concurrency and a board-level serialization lock.

    The board lock serializes card moves made through this service. Callers must
    authenticate actor before invoking it, and cannot choose a board by arbitrary ID.
    """
    if actor is None or not actor.is_authenticated:
        raise PermissionDenied("Authentication required")
    if type(expected_version) is not int or expected_version < 0:
        raise ValidationError("expected_version must be a non-negative integer")

    # Read the board ID only; authorization is checked on the locked parent.
    card_board_id = Card.objects.filter(pk=card_id).values_list("board_id", flat=True).first()
    if card_board_id is None:
        raise Card.DoesNotExist()
    board = Board.objects.select_for_update().get(pk=card_board_id)
    if board.owner_id != actor.pk:
        raise PermissionDenied("Card is not accessible")

    card = Card.objects.select_for_update().get(pk=card_id, board=board)
    if card.version != expected_version:
        raise ValidationError("Stale card version")
    target = Column.objects.filter(pk=target_column_id, board=board).first()
    if target is None:
        raise ValidationError("Target column must belong to this board")
    if card.column_id == target.pk:
        return card

    previous = card.column
    card.column = target
    card.position = (
        Card.objects.filter(column=target).aggregate(max_position=models.Max("position"))[
            "max_position"
        ] or 0
    ) + 1
    card.version += 1
    card.save(update_fields=("column", "position", "version", "updated_at"))
    CardMove.objects.create(
        card=card,
        actor=actor,
        from_column=previous,
        to_column=target,
        version=card.version,
    )
    return card
