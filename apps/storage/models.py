"""Private uploaded objects, separate from the storage backend's object lifecycle."""

import uuid

from django.conf import settings
from django.db import models


class StoredFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="stored_files"
    )
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    object_key = models.CharField(max_length=160, unique=True, editable=False)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["organization", "owner", "-created_at"], name="storage_org_owner_time_idx"),
            models.Index(fields=["organization", "-created_at"], name="storage_org_time_idx"),
        ]

    def __str__(self):
        return f"{self.id}: {self.original_name}"
