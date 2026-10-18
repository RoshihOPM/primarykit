"""Owner-private people/organizations; no external CRM foreign keys."""

from django.conf import settings
from django.db import models

from apps.core.models import UUIDTimestampedModel


class Contact(UUIDTimestampedModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    name = models.CharField(max_length=160)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    company = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("owner", "-created_at"), name="contacts_owner_idx"),
        ]
