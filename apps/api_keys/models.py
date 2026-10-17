"""Copied clients own every schema migration."""

import uuid

from django.conf import settings
from django.db import models


class ApiKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="machine_api_keys"
    )
    name = models.CharField(max_length=80)
    secret_digest = models.CharField(max_length=64, editable=False)
    scopes = models.JSONField(default=list)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=("owner", "revoked_at"), name="apikeys_owner_state_idx"),
        ]

    def __str__(self):
        return f"ApiKey {self.pk}"
