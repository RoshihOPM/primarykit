"""Warehouse stock: balances are transactional materializations of an append-only ledger."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.catalog.models import CatalogItem
from apps.core.models import UUIDTimestampedModel


class Warehouse(UUIDTimestampedModel):
    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)


class StockBalance(UUIDTimestampedModel):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="balances")
    item = models.ForeignKey(CatalogItem, on_delete=models.PROTECT, related_name="stock_balances")
    on_hand = models.PositiveBigIntegerField(default=0)
    reserved = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("warehouse", "item"), name="inventory_balance_unique"),
            models.CheckConstraint(condition=Q(on_hand__gte=F("reserved")), name="inventory_reserve_lte_onhand"),
        ]
        indexes = [models.Index(fields=["item", "warehouse"], name="inventory_item_warehouse_idx")]

    @property
    def available(self):
        return self.on_hand - self.reserved


class StockReservation(UUIDTimestampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RELEASED = "released", "Released"
        CONSUMED = "consumed", "Consumed"

    balance = models.ForeignKey(StockBalance, on_delete=models.PROTECT, related_name="reservations")
    quantity = models.PositiveBigIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="inventory_reservation_qty_pos"),
        ]


class InventoryOperation(UUIDTimestampedModel):
    key = models.CharField(max_length=128, unique=True)
    fingerprint = models.CharField(max_length=64)
    kind = models.CharField(max_length=20)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    result = models.JSONField(default=dict)

    class Meta:
        ordering = ("-created_at",)


class ImmutableMovementQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Stock movements are immutable.")

    def delete(self):
        raise ValidationError("Stock movements cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Stock movements cannot be modified.")


class StockMovement(UUIDTimestampedModel):
    operation = models.ForeignKey(InventoryOperation, on_delete=models.PROTECT, related_name="movements")
    balance = models.ForeignKey(StockBalance, on_delete=models.PROTECT, related_name="movements")
    kind = models.CharField(max_length=20)
    on_hand_delta = models.BigIntegerField(default=0)
    reserved_delta = models.BigIntegerField(default=0)

    objects = ImmutableMovementQuerySet.as_manager()

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=~(Q(on_hand_delta=0) & Q(reserved_delta=0)),
                name="inventory_movement_nonzero",
            ),
        ]
        indexes = [
            models.Index(fields=["balance", "created_at"], name="inventory_movement_balance_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Stock movements are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Stock movements cannot be deleted.")
