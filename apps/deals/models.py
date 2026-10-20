"""Private deal lifecycle; values are not settlement or invoices."""

from django.conf import settings
from django.db import models

from apps.core.models import UUIDTimestampedModel


class Deal(UUIDTimestampedModel):
    class Stage(models.TextChoices):
        OPEN = "open", "Open"
        NEGOTIATION = "negotiation", "Negotiation"
        WON = "won", "Won"
        LOST = "lost", "Lost"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    title = models.CharField(max_length=200)
    amount_minor = models.PositiveBigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="USD")
    notes = models.TextField(blank=True)
    stage = models.CharField(max_length=16, choices=Stage.choices, default=Stage.OPEN)
    version = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("owner", "stage", "-created_at"), name="deals_owner_stage_idx")
        ]
