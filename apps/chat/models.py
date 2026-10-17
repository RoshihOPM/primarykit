"""One-to-one dialogues with tenant-aware scope and monotonic message sequence."""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import UUIDTimestampedModel


class Dialogue(UUIDTimestampedModel):
    user_low = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    user_high = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    # Stable, non-null unique key: SQL NULLs are not distinct for uniqueness.
    scope_key = models.CharField(max_length=40, default="personal", editable=False)
    organization_id = models.UUIDField(null=True, blank=True, db_index=True)
    last_sequence = models.PositiveBigIntegerField(default=0)
    low_read_sequence = models.PositiveBigIntegerField(default=0)
    high_read_sequence = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("scope_key", "user_low", "user_high"), name="chat_unique_pair_scope"
            ),
            models.CheckConstraint(
                condition=Q(user_low_id__lt=F("user_high_id")), name="chat_ordered_pair"
            ),
        ]
        indexes = [
            models.Index(fields=("user_low", "-updated_at"), name="chat_low_recent_idx"),
            models.Index(fields=("user_high", "-updated_at"), name="chat_high_recent_idx"),
        ]


class Message(UUIDTimestampedModel):
    dialogue = models.ForeignKey(Dialogue, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    sequence = models.PositiveBigIntegerField()
    body = models.TextField(blank=True)
    # Opaque ID validated at write and read boundaries; Storage is optional.
    attachment_id = models.UUIDField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ("sequence",)
        constraints = [
            models.UniqueConstraint(
                fields=("dialogue", "sequence"), name="chat_message_sequence_unique"
            ),
            models.CheckConstraint(condition=Q(sequence__gte=1), name="chat_sequence_positive"),
        ]
