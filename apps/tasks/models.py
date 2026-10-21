"""Internal durable work queue. Models keep a reviewed source-owned migration baseline."""

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


class JobSchedule(models.Model):
    """Recurring wall-clock definition; firing produces BackgroundJob rows."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    namespace = models.CharField(max_length=80, default="default")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=100)
    payload = models.JSONField()
    timezone_name = models.CharField(max_length=64, default="UTC")
    hour = models.PositiveSmallIntegerField()
    minute = models.PositiveSmallIntegerField()
    weekdays = models.JSONField(default=list, blank=True)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    next_run_at = models.DateTimeField()
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("namespace", "name"), name="tasks_schedule_name_uniq"),
            models.CheckConstraint(
                condition=Q(hour__gte=0) & Q(hour__lte=23),
                name="tasks_schedule_hour_valid",
            ),
            models.CheckConstraint(
                condition=Q(minute__gte=0) & Q(minute__lte=59),
                name="tasks_schedule_minute_valid",
            ),
            models.CheckConstraint(
                condition=Q(max_attempts__gte=1) & Q(max_attempts__lte=10),
                name="tasks_schedule_attempts_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("is_enabled", "next_run_at"), name="tasks_schedule_due_idx"),
        ]

    def __str__(self):
        return f"{self.namespace}:{self.name}"
