"""Organization-bound warehouse balances and immutable movement ledger."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.catalog.models import CatalogItem
from apps.core.models import UUIDTimestampedModel
from apps.organizations.models import Branch, Organization


class Warehouse(UUIDTimestampedModel):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="warehouses"
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name="warehouses"
    )
    code = models.SlugField(max_length=80)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "code"), name="inventory_warehouse_org_code_uniq"
            )
        ]

    def save(self, *args, **kwargs):
        if self.branch_id and self.organization_id:
            branch_org = Branch.objects.filter(pk=self.branch_id).values_list(
                "organization_id", flat=True
            ).first()
            if branch_org != self.organization_id:
                raise ValidationError("Warehouse branch must belong to its organization.")
        return super().save(*args, **kwargs)


class StockBalance(UUIDTimestampedModel):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="stock_balances"
    )
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="balances")
    item = models.ForeignKey(CatalogItem, on_delete=models.PROTECT, related_name="stock_balances")
    on_hand = models.PositiveBigIntegerField(default=0)
    reserved = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "warehouse", "item"), name="inventory_balance_unique"
            ),
            models.CheckConstraint(
                condition=Q(on_hand__gte=F("reserved")), name="inventory_reserve_lte_onhand"
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "item", "warehouse"],
                name="inventory_org_item_wh_idx",
            )
        ]

    @property
    def available(self):
        return self.on_hand - self.reserved

    def save(self, *args, **kwargs):
        if self.organization_id and self.warehouse_id and self.item_id:
            warehouse_org = Warehouse.objects.filter(pk=self.warehouse_id).values_list(
                "organization_id", flat=True
            ).first()
            item_org = CatalogItem.objects.filter(pk=self.item_id).values_list(
                "organization_id", flat=True
            ).first()
            if self.organization_id != warehouse_org or self.organization_id != item_org:
                raise ValidationError("Balance, warehouse and item must belong to one organization.")
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
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="inventory_reservation_qty_pos"
            ),
        ]


class InventoryOperation(UUIDTimestampedModel):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="inventory_operations"
    )
    key = models.CharField(max_length=128)
    fingerprint = models.CharField(max_length=64)
    kind = models.CharField(max_length=20)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    result = models.JSONField(default=dict)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "key"), name="inventory_operation_org_key_uniq"
            )
        ]


class ImmutableMovementQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Stock movements are immutable.")

    def delete(self):
        raise ValidationError("Stock movements cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Stock movements cannot be modified.")


class StockMovement(UUIDTimestampedModel):
    operation = models.ForeignKey(
        InventoryOperation, on_delete=models.PROTECT, related_name="movements"
    )
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
