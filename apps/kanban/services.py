"""Owner-scoped, versioned Kanban operations."""

from django.db import models, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from .models import Board, Card, CardMove, Column


class StaleCard(ValidationError):
    status_code = 409
    default_detail = "Card has changed; refresh and retry."


def _locked_card(actor, card_id):
    board_id = (
        Card.objects.filter(pk=card_id, board__owner=actor)
        .values_list("board_id", flat=True)
        .first()
    )
    if board_id is None:
        raise NotFound()
    board = Board.objects.select_for_update().get(pk=board_id, owner=actor)
    card = Card.objects.select_for_update().get(pk=card_id, board=board)
    return board, card


@transaction.atomic
def edit_card(*, actor, card_id, expected_version, changes):
    _, card = _locked_card(actor, card_id)
    if card.version != expected_version:
        raise StaleCard()
    if not changes:
        raise ValidationError("No changes provided.")
    for key in changes:
        if key not in {"title", "description"}:
            raise ValidationError({key: "Field is not editable."})
    for key, value in changes.items():
        setattr(card, key, value)
    card.version += 1
    card.save(update_fields=(*changes.keys(), "version", "updated_at"))
    return card


@transaction.atomic
def move_card(*, actor, card_id, target_column_id, expected_version, position=None):
    board, card = _locked_card(actor, card_id)
    if card.version != expected_version:
        raise StaleCard()
    target = Column.objects.filter(pk=target_column_id, board=board).first()
    if target is None:
        raise ValidationError({"target_column_id": "Column must belong to this board."})
    if position is not None and (type(position) is not int or position < 0):
        raise ValidationError({"position": "Expected a non-negative integer."})

    # All writers using this service serialize on the board. Reorder both affected
    # columns as dense integer positions, bumping affected card versions.
    same_column = card.column_id == target.pk
    if same_column and position is None:
        return card
    source = list(
        Card.objects.filter(column_id=card.column_id).order_by("position", "created_at", "pk")
    )
    destination = (
        source
        if same_column
        else list(Card.objects.filter(column=target).order_by("position", "created_at", "pk"))
    )
    source = [item for item in source if item.pk != card.pk]
    if same_column:
        destination = source
    index = len(destination) if position is None else min(position, len(destination))
    destination.insert(index, card)
    previous_column = card.column
    now = timezone.now()
    touched = {}
    for column, items in (
        ((target, destination),)
        if same_column
        else ((previous_column, source), (target, destination))
    ):
        for offset, item in enumerate(items):
            new_column_id = column.pk
            if item.position != offset or item.column_id != new_column_id:
                item.column_id = new_column_id
                item.position = offset
                item.version += 1
                item.updated_at = now
                touched[item.pk] = item
    if card.pk not in touched:
        return card
    Card.objects.bulk_update(
        list(touched.values()), ["column", "position", "version", "updated_at"]
    )
    if not same_column:
        CardMove.objects.create(
            card=card,
            actor=actor,
            from_column=previous_column,
            to_column=target,
            version=card.version,
        )
    return card


@transaction.atomic
def create_card(*, actor, board_id, column_id, title, description=""):
    board = Board.objects.select_for_update().filter(pk=board_id, owner=actor).first()
    if board is None:
        raise NotFound()
    column = Column.objects.filter(pk=column_id, board=board).first()
    if column is None:
        raise ValidationError({"column": "Column must belong to the board."})
    max_position = Card.objects.filter(column=column).aggregate(value=models.Max("position"))[
        "value"
    ]
    return Card.objects.create(
        board=board,
        column=column,
        title=title,
        description=description,
        position=(max_position + 1 if max_position is not None else 0),
    )


class StaleColumn(ValidationError):
    status_code = 409
    default_detail = "Column order has changed; refresh and retry."


@transaction.atomic
def create_column(*, actor, board_id, name):
    board = Board.objects.select_for_update().filter(pk=board_id, owner=actor).first()
    if board is None:
        raise NotFound()
    last = Column.objects.filter(board=board).aggregate(value=models.Max("position"))["value"]
    return Column.objects.create(board=board, name=name, position=0 if last is None else last + 1)


@transaction.atomic
def reorder_column(*, actor, column_id, expected_position, position):
    column_board_id = (
        Column.objects.filter(pk=column_id, board__owner=actor)
        .values_list("board_id", flat=True)
        .first()
    )
    if column_board_id is None:
        raise NotFound()
    board = Board.objects.select_for_update().get(pk=column_board_id, owner=actor)
    columns = list(Column.objects.filter(board=board).order_by("position", "created_at", "pk"))
    moving = next(column for column in columns if column.pk == column_id)
    if moving.position != expected_position:
        raise StaleColumn()
    columns.remove(moving)
    columns.insert(min(position, len(columns)), moving)
    changed = []
    for index, item in enumerate(columns):
        if item.position != index:
            item.position = index
            changed.append(item)
    if changed:
        Column.objects.bulk_update(changed, ["position"])
    return moving
