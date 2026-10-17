"""Trusted provisioning plus PostgreSQL-only atomic accounting.

No Django superuser bypass. Organizations integration is imported only when installed.
Do not call quota provisioning from untrusted API inputs, including payment callbacks.
"""

import hashlib
import uuid
from dataclasses import dataclass

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import NotSupportedError, connection, transaction
from django.db.models import F, Q
from django.utils import timezone
from rest_framework.exceptions import NotFound

from .domain import (
    QuotaConflict,
    QuotaExceeded,
    QuotaRuleError,
    is_in_window,
    normalize_metadata,
    validate_code,
    validate_event_key,
    validate_units,
    validate_window,
)
from .models import UsageCounter, UsageEvent, UsagePolicy


@dataclass(frozen=True)
class UsageResult:
    policy_id: uuid.UUID
    code: str
    used_units: int
    limit_units: int
    remaining_units: int
    replayed: bool


def _require_postgres() -> None:
    if connection.vendor != "postgresql":
        raise NotSupportedError("Durable usage accounting requires PostgreSQL.")


def _scope_id(value) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise QuotaRuleError("Invalid scope identifier.") from exc


def _parse_policy_id(value) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise NotFound() from exc


def _authorized(*, actor, policy: UsagePolicy) -> None:
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise NotFound()
    if policy.scope == UsagePolicy.Scope.OWNER:
        if actor.pk != policy.owner_id:
            raise NotFound()
        return
    if policy.scope != UsagePolicy.Scope.TENANT or not apps.is_installed("apps.organizations"):
        raise NotFound()
    from apps.organizations.models import Organization
    from apps.organizations.permissions import get_active_membership

    org = Organization.objects.filter(pk=policy.tenant_id, is_active=True).first()
    if org is None:
        raise NotFound()
    get_active_membership(user=actor, organization=org)


def _snapshot(policy: UsagePolicy) -> dict:
    return {
        "scope": policy.scope,
        "scope_id": str(policy.owner_id or policy.tenant_id),
        "code": policy.code,
        "limit_units": policy.limit_units,
        "period_start": policy.period_start.isoformat(),
        "period_end": policy.period_end.isoformat(),
        "expires_at": policy.expires_at.isoformat() if policy.expires_at else None,
        "metadata": policy.metadata,
    }


def provision_quota(
    *, scope: str, scope_id, code: str, period_start, period_end,
    limit_units: int, expires_at=None, metadata=None,
) -> UsagePolicy:
    """TRUSTED SERVER ONLY. Clients decide their own entitlements and time windows.

    Serialize policy provisioning per (scope, identity, code) with a transaction-level
    PostgreSQL advisory lock, so overlapping windows cannot be created concurrently.
    Policies are immutable after creation. Grant a new non-overlapping window instead.
    """
    if scope not in (UsagePolicy.Scope.OWNER, UsagePolicy.Scope.TENANT):
        raise QuotaRuleError("Scope must be owner or tenant.")
    identifier = _scope_id(scope_id)
    code = validate_code(code)
    validate_units(limit_units, allow_zero=True)
    validate_window(period_start, period_end, expires_at)
    metadata = normalize_metadata(metadata)
    _require_postgres()
    lookup = {"owner_id": identifier} if scope == UsagePolicy.Scope.OWNER else {
        "tenant_id": identifier
    }
    if scope == UsagePolicy.Scope.OWNER:
        if not get_user_model().objects.filter(pk=identifier, is_active=True).exists():
            raise QuotaRuleError("Scope owner does not exist or is inactive.")
    else:
        if not apps.is_installed("apps.organizations"):
            raise QuotaRuleError("Tenant quotas require the Organizations module.")
        from apps.organizations.models import Organization

        if not Organization.objects.filter(pk=identifier, is_active=True).exists():
            raise QuotaRuleError("Tenant does not exist or is inactive.")
    lock_key = int.from_bytes(
        hashlib.sha256(f"{scope}:{identifier}:{code}".encode()).digest()[:8],
        "big", signed=True,
    )
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])
        overlapping = UsagePolicy.objects.filter(
            scope=scope, code=code, period_start__lt=period_end,
            period_end__gt=period_start, **lookup,
        ).exists()
        if overlapping:
            raise QuotaConflict("Overlapping policy windows are not permitted.")
        policy = UsagePolicy.objects.create(
            scope=scope, code=code, period_start=period_start, period_end=period_end,
            expires_at=expires_at, limit_units=limit_units, metadata=metadata, **lookup,
        )
        UsageCounter.objects.create(policy=policy)
        return policy


def get_quota_status(*, actor, policy_id) -> UsageResult:
    """Read a policy's current counter with explicit actor scope authorization."""
    policy = UsagePolicy.objects.filter(pk=_parse_policy_id(policy_id)).first()
    if policy is None:
        raise NotFound()
    _authorized(actor=actor, policy=policy)
    used = UsageCounter.objects.get(policy=policy).used_units
    return UsageResult(
        policy.id, policy.code, used, policy.limit_units,
        policy.limit_units - used, False,
    )


def find_current_quota(*, actor, code: str, tenant_id=None) -> UsagePolicy:
    """Resolve one active policy. Multiple matching windows fail closed."""
    code = validate_code(code)
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise NotFound()
    now = timezone.now()
    if tenant_id is None:
        lookup = {"scope": UsagePolicy.Scope.OWNER, "owner_id": actor.pk}
    else:
        identifier = _scope_id(tenant_id)
        if not apps.is_installed("apps.organizations"):
            raise NotFound()
        from apps.organizations.models import Organization
        from apps.organizations.permissions import get_active_membership

        org = Organization.objects.filter(pk=identifier, is_active=True).first()
        if org is None:
            raise NotFound()
        get_active_membership(user=actor, organization=org)
        lookup = {"scope": UsagePolicy.Scope.TENANT, "tenant_id": identifier}
    policies = list(UsagePolicy.objects.filter(
        code=code, period_start__lte=now, period_end__gt=now, **lookup,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))[:2])
    if not policies:
        raise NotFound()
    if len(policies) > 1:
        raise QuotaConflict("Ambiguous active usage policies.")
    return policies[0]


def consume_usage(*, actor, policy_id, event_key: str, units: int = 1) -> UsageResult:
    """Atomic compare-and-increment, event insert and replay within one commit.

    A retry MUST target the same policy_id, even across billing period boundaries.
    Concurrent different keys serialize on the policy row; the UPDATE also bounds
    the increment. The original event is replayable after expiration.
    """
    units = validate_units(units)
    event_key = validate_event_key(event_key)
    _require_postgres()
    with transaction.atomic():
        policy = UsagePolicy.objects.select_for_update().filter(
            pk=_parse_policy_id(policy_id)
        ).first()
        if policy is None:
            raise NotFound()
        _authorized(actor=actor, policy=policy)
        event = UsageEvent.objects.filter(policy=policy, event_key=event_key).first()
        if event is not None:
            if event.units != units:
                raise QuotaConflict("Event key reused with different units.")
            return UsageResult(
                policy.id, policy.code, event.used_after, event.policy_snapshot["limit_units"],
                event.policy_snapshot["limit_units"] - event.used_after, True,
            )
        now = timezone.now()
        if not is_in_window(
            now=now, start=policy.period_start, end=policy.period_end,
            expires_at=policy.expires_at,
        ):
            raise QuotaRuleError("Quota window is closed or expired.")
        if units > policy.limit_units:
            raise QuotaExceeded("Quota exceeded.")
        updated = UsageCounter.objects.filter(
            policy=policy, used_units__lte=policy.limit_units - units,
        ).update(used_units=F("used_units") + units)
        if updated != 1:
            raise QuotaExceeded("Quota exceeded.")
        used_after = UsageCounter.objects.values_list("used_units", flat=True).get(policy=policy)
        UsageEvent.objects.create(
            policy=policy, event_key=event_key, units=units,
            used_after=used_after, policy_snapshot=_snapshot(policy),
        )
        return UsageResult(
            policy.id, policy.code, used_after, policy.limit_units,
            policy.limit_units - used_after, False,
        )
