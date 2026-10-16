"""Internal durable work queue. Models and migrations belong to copied clients."""

import uuid

from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class BackgroundJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        RUNNING = "running"
        SUCCEEDED = "succeeded"
        FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    namespace = models.CharField(max_length=80, default="default")
    code = models.CharField(max_length=100)
    payload = models.JSONField()
    idempotency_key = models.CharField(max_length=128, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    available_at = models.DateTimeField(default=timezone.now)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    locked_at = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)
    last_error = models.CharField(max_length=160, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(max_attempts__gte=1) & Q(max_attempts__lte=10),
                name="tasks_max_attempts_valid",
            ),
            models.CheckConstraint(
                condition=Q(attempts__lte=F("max_attempts")),
                name="tasks_attempts_not_exceeded",
            ),
            models.UniqueConstraint(
                fields=("namespace", "idempotency_key"), name="tasks_namespace_idempotency"
            ),
        ]
        indexes = [
            models.Index(fields=("status", "available_at", "created_at"), name="tasks_ready_idx"),
            models.Index(fields=("status", "locked_at"), name="tasks_lease_idx"),
        ]

    def __str__(self):
        return f"{self.code} ({self.status})"
