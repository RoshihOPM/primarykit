"""Reusable, client-owned Kanban state. No generic public endpoints by default."""

from django.conf import settings
from django.db import models

from apps.core.models import UUIDTimestampedModel


class Board(UUIDTimestampedModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    name = models.CharField(max_length=160)

    class Meta:
        indexes = [models.Index(fields=("owner", "-created_at"), name="kanban_board_owner_idx")]


class Column(UUIDTimestampedModel):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="columns")
    name = models.CharField(max_length=100)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "created_at", "pk")
        indexes = [models.Index(fields=("board", "position"), name="kanban_column_order_idx")]


class Card(UUIDTimestampedModel):
    """Self-contained card; clients can extend with their own domain entity mappings."""

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="cards")
    column = models.ForeignKey(Column, on_delete=models.PROTECT, related_name="cards")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    version = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "created_at", "pk")
        indexes = [models.Index(fields=("column", "position"), name="kanban_card_order_idx")]


class CardMove(UUIDTimestampedModel):
    """Append-only through the service layer; clients decide retention."""

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="moves")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    from_column = models.ForeignKey(Column, on_delete=models.PROTECT, related_name="+")
    to_column = models.ForeignKey(Column, on_delete=models.PROTECT, related_name="+")
    version = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("card", "version"), name="kanban_card_move_version_uq")
        ]
