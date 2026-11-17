"""Deduplicate verified inbound deliveries in the client's own PostgreSQL DB.

Each processed delivery stores two rows per provider in ``delivery_hash``:
sha256 of the caller-supplied delivery ID and a domain-separated sha256 of the
verified signature (see ``apps.webhooks.inbound``).
"""

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
