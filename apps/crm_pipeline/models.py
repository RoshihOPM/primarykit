"""Explicit opt-in mapping, not a source-of-truth Deal stage."""

from django.conf import settings
from django.db import models

from apps.core.models import UUIDTimestampedModel


class DealCardLink(UUIDTimestampedModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    deal = models.OneToOneField("deals.Deal", on_delete=models.PROTECT, related_name="+")
    card = models.OneToOneField("kanban.Card", on_delete=models.PROTECT, related_name="+")

    class Meta:
        indexes = [models.Index(fields=("owner", "-created_at"), name="crm_pipeline_owner_idx")]
