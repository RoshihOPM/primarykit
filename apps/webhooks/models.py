"""Deduplicate verified inbound deliveries in the client's own PostgreSQL DB."""

from django.db import models


class InboundReceipt(models.Model):
    provider = models.CharField(max_length=80)
    delivery_hash = models.CharField(max_length=64)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "delivery_hash"), name="webhooks_provider_delivery"
            )
        ]
        indexes = [
            models.Index(fields=("received_at",), name="webhooks_received_idx"),
        ]
