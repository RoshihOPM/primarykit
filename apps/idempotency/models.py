"""Generated clients own migrations and retention for idempotency receipts."""

from django.db import models


class CommandReceipt(models.Model):
    scope = models.CharField(max_length=160)
    key = models.CharField(max_length=128)
    request_digest = models.CharField(max_length=64)
    response = models.JSONField(null=True)
    completed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("scope", "key"), name="idem_scope_key_unique"),
        ]
        indexes = [
            models.Index(fields=("created_at",), name="idem_created_idx"),
        ]
