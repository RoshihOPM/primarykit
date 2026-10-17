"""Client-owned schema; migrations are generated and committed in each project."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class UsagePolicy(models.Model):
    """Immutable quota contract for one explicit time window and security scope."""

    class Scope(models.TextChoices):
        OWNER = "owner", "Owner"
        TENANT = "tenant", "Tenant"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=6, choices=Scope.choices)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="usage_policies",
    )
    # No FK to optional Organizations: an owner-only project must be independent.
    tenant_id = models.UUIDField(null=True, blank=True)
    code = models.CharField(max_length=64)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)
    limit_units = models.PositiveBigIntegerField()
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(scope="owner", owner__isnull=False, tenant_id__isnull=True)
                    | Q(scope="tenant", owner__isnull=True, tenant_id__isnull=False)
                ),
                name="usage_exactly_one_scope_ck",
            ),
            models.CheckConstraint(
                condition=Q(period_end__gt=F("period_start")),
                name="usage_valid_window_ck",
            ),
            models.CheckConstraint(
                condition=Q(limit_units__gte=0),
                name="usage_nonnegative_limit_ck",
            ),
            models.UniqueConstraint(
                fields=("owner", "code", "period_start"),
                name="usage_owner_period_uq",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "code", "period_start"),
                name="usage_tenant_period_uq",
            ),
        ]
        indexes = [
            models.Index(fields=("owner", "code", "period_end"), name="usage_owner_lookup_idx"),
            models.Index(
                fields=("tenant_id", "code", "period_end"), name="usage_tenant_lookup_idx"
            ),
        ]


class UsageCounter(models.Model):
    policy = models.OneToOneField(
        UsagePolicy, primary_key=True, on_delete=models.PROTECT, related_name="counter"
    )
    used_units = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(used_units__gte=0), name="usage_nonnegative_used_ck"
            ),
        ]


class UsageEvent(models.Model):
    """Idempotent committed spend. Never mutate or delete while replay is required."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    policy = models.ForeignKey(UsagePolicy, on_delete=models.PROTECT, related_name="events")
    event_key = models.CharField(max_length=128)
    units = models.PositiveBigIntegerField()
    used_after = models.PositiveBigIntegerField()
    policy_snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("policy", "event_key"), name="usage_policy_event_key_uq"
            ),
            models.CheckConstraint(condition=Q(units__gt=0), name="usage_positive_event_units_ck"),
        ]
        indexes = [models.Index(fields=("created_at",), name="usage_event_created_idx")]
