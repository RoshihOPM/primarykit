"""Independent sale ledger; optional Order link is an opaque UUID, not an FK."""

from django.conf import settings
from django.db import models

from apps.core.models import UUIDTimestampedModel


class Sale(UUIDTimestampedModel):
    class Status(models.TextChoices):
        RECORDED = "recorded", "Recorded"
        VOIDED = "voided", "Voided"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RECORDED)
    currency = models.CharField(max_length=3)
    total_minor = models.PositiveBigIntegerField()
    source_order_id = models.UUIDField(null=True, blank=True, db_index=True)
    idempotency_key = models.CharField(max_length=128)
    fingerprint = models.CharField(max_length=64)
    voided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "idempotency_key"), name="sales_owner_idempotency_unique"
            ),
            models.UniqueConstraint(
                fields=("owner", "source_order_id"), name="sales_owner_order_unique"
            ),
        ]


class SaleLineItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="lines")
    sku = models.CharField(max_length=80)
    title = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField()
    unit_price_minor = models.PositiveBigIntegerField()
    line_total_minor = models.PositiveBigIntegerField()

    class Meta:
        ordering = ("pk",)
