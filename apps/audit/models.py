"""Application audit events: append-only through normal Django ORM operations."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ImmutableAuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Audit events cannot be modified.")

    def delete(self):
        raise ValidationError("Audit events cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Audit events cannot be modified.")


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    action = models.CharField(max_length=128)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=128)
    changes = models.JSONField(default=dict, blank=True)

    objects = ImmutableAuditQuerySet.as_manager()

    class Meta:
        ordering = ("-occurred_at", "-id")
        indexes = [
            models.Index(fields=["action", "-occurred_at"], name="audit_action_time_idx"),
            models.Index(
                fields=["target_type", "target_id", "-occurred_at"],
                name="audit_target_time_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Audit events cannot be modified.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events cannot be deleted.")

    def __str__(self):
        return f"{self.action} {self.target_type}:{self.target_id}"
