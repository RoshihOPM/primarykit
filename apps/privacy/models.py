"""Only privacy orchestration metadata; never cascades into business entities."""

import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone


class PrivacySubject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=80)
    kind = models.CharField(max_length=64)
    reference = models.UUIDField()
    legal_hold = models.BooleanField(default=False)
    hold_reason = models.CharField(max_length=16, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("scope", "kind", "reference"),
                                    name="privacy_unique_subject"),
        ]


class PrivacyRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        HELD = "held"
        COMPLETED = "completed"
        CANCELLED = "cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.ForeignKey(PrivacySubject, on_delete=models.PROTECT,
                                related_name="requests")
    idempotency_key = models.UUIDField(unique=True)
    policy_code = models.CharField(max_length=64)
    policy_fingerprint = models.CharField(max_length=64)
    action = models.CharField(max_length=12, choices=[(s, s) for s in
                              ("redact", "anonymize", "delete")])
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    execute_after = models.DateTimeField()
    revision = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("subject",),
                                    condition=Q(status__in=("pending", "held")),
                                    name="privacy_one_active_request"),
            models.CheckConstraint(condition=Q(revision__gte=0),
                                   name="privacy_revision_nonnegative"),
        ]
        indexes = [
            models.Index(fields=("status", "execute_after"), name="privacy_due_idx"),
        ]
