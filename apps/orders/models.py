"""Order owner and immutable product/price snapshots (not Catalog foreign keys)."""

from django.conf import settings
from django.db import models

from apps.core.models import UUIDTimestampedModel


class Order(UUIDTimestampedModel):
    class Status(models.TextChoices):
        PLACED = "placed", "Placed"
        CANCELED = "canceled", "Canceled"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLACED)
    currency = models.CharField(max_length=3)
    total_minor = models.PositiveBigIntegerField()
    idempotency_key = models.CharField(max_length=128)
    fingerprint = models.CharField(max_length=64)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "idempotency_key"), name="orders_owner_idempotency_unique"
            ),
        ]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="items")
    sku = models.CharField(max_length=80)
    title = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField()
    unit_price_minor = models.PositiveBigIntegerField()
    line_total_minor = models.PositiveBigIntegerField()

    class Meta:
        ordering = ("pk",)
