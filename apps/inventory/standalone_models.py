"""Independent warehouse and stock models: no Catalog or Organizations imports."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from apps.core.models import UUIDTimestampedModel


class InventoryItem(UUIDTimestampedModel):
    """Inventory-owned SKU; optional external catalog mapping is an integration."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    sku = models.CharField(max_length=80)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sku",)
        constraints = [
            models.UniqueConstraint(Lower("sku"), "owner", name="inventory_owner_sku_unique")
        ]

    def save(self, *args, **kwargs):
        self.sku = self.sku.strip().upper()
        if not self.sku:
            raise ValidationError("SKU cannot be empty.")
        return super().save(*args, **kwargs)


class Warehouse(UUIDTimestampedModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    code = models.SlugField(max_length=80)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(fields=("owner", "code"), name="inventory_owner_wh_code")
        ]


class StockBalance(UUIDTimestampedModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="balances")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="balances")
    on_hand = models.PositiveBigIntegerField(default=0)
    reserved = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "warehouse", "item"), name="inventory_personal_balance_unique"
            ),
            models.CheckConstraint(
                condition=Q(on_hand__gte=F("reserved")), name="inventory_reserve_lteonhand"
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "item", "warehouse"], name="inventory_personal_item")
        ]

    @property
    def available(self):
        return self.on_hand - self.reserved

    def save(self, *args, **kwargs):
        if self.owner_id and self.warehouse_id and self.item_id:
            if (
                Warehouse.objects.filter(pk=self.warehouse_id, owner_id=self.owner_id).exists()
                and InventoryItem.objects.filter(pk=self.item_id, owner_id=self.owner_id).exists()
            ):
                return super().save(*args, **kwargs)
            raise ValidationError("Warehouse, item and stock balance must have one owner.")
        return super().save(*args, **kwargs)


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
            models.CheckConstraint(condition=Q(quantity__gt=0), name="inventory_reserve_qty_positive")
        ]


class InventoryOperation(UUIDTimestampedModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    key = models.CharField(max_length=128)
    fingerprint = models.CharField(max_length=64)
    kind = models.CharField(max_length=20)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    result = models.JSONField(default=dict)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("owner", "key"), name="inventory_personal_op_key")
        ]


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
            models.Index(fields=["balance", "created_at"], name="inventory_movement_balance_idx")
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Stock movements are immutable.")
        if self.operation_id and self.balance_id:
            op_owner = (
                InventoryOperation.objects.filter(pk=self.operation_id)
                .values_list("owner_id", flat=True)
                .first()
            )
            balance_owner = (
                StockBalance.objects.filter(pk=self.balance_id)
                .values_list("owner_id", flat=True)
                .first()
            )
            if op_owner != balance_owner:
                raise ValidationError("Movement operation and balance must have the same owner.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Stock movements cannot be deleted.")
