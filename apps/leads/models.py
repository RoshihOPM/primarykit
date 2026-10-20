"""CRM leads with a single authoritative lifecycle state."""

from django.conf import settings
from django.db import models

from apps.core.models import UUIDTimestampedModel


class Lead(UUIDTimestampedModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        QUALIFIED = "qualified", "Qualified"
        WON = "won", "Won"
        LOST = "lost", "Lost"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
        null=True, blank=True,
    )
    title = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=160)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    source = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    version = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("owner", "status", "-created_at"), name="leads_owner_status_idx"),
            models.Index(fields=("owner", "source", "-created_at"), name="leads_owner_source_idx"),
        ]
