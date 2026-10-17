"""Negative authorization, storage and PostgreSQL quota invariants."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import NotSupportedError, connection
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.usage_quotas.domain import QuotaConflict, QuotaExceeded, QuotaRuleError
from apps.usage_quotas.models import UsageCounter, UsageEvent, UsagePolicy
from apps.usage_quotas.services import (
    consume_usage,
    find_current_quota,
    get_quota_status,
    provision_quota,
)
from apps.users.models import User

pytestmark = pytest.mark.django_db


def user(email, **kwargs):
    return User.objects.create_user(
        email=email, password="Sample-long-test-password-1", email_verified=True, **kwargs
    )


def window():
    now = timezone.now()
    return now - timedelta(hours=1), now + timedelta(days=1)


def grant(actor, *, limit=3, **kwargs):
    start, end = window()
    return provision_quota(
        scope="owner",
        scope_id=actor.pk,
        code="requests",
        period_start=start,
        period_end=end,
        limit_units=limit,
        **kwargs,
    )


def postgresql_only():
    if connection.vendor != "postgresql":
        pytest.skip("Atomic usage accounting requires PostgreSQL")


def test_sqlite_rejects_accounting_without_claiming_atomicity():
    if connection.vendor == "postgresql":
        pytest.skip("PostgreSQL-specific behavior is covered below")
    actor = user("sqlite@quota.test")
    start, end = window()
    with pytest.raises(NotSupportedError):
        provision_quota(
            scope="owner",
            scope_id=actor.pk,
            code="requests",
            period_start=start,
            period_end=end,
            limit_units=2,
        )
    with pytest.raises(NotSupportedError):
        consume_usage(actor=actor, policy_id=uuid4(), event_key="event-1")


def test_personal_quota_idor_including_superuser_and_failed_mutation():
    postgresql_only()
    owner = user("quota-owner@tests.test")
    outsider = user("quota-outsider@tests.test")
    elevated = user("quota-global@tests.test", is_staff=True, is_superuser=True)
    policy = grant(owner)
    for actor in (outsider, elevated, None):
        with pytest.raises(NotFound):
            get_quota_status(actor=actor, policy_id=policy.pk)
        with pytest.raises(NotFound):
            consume_usage(actor=actor, policy_id=policy.pk, event_key="exploit", units=1)
    with pytest.raises(NotFound):
        find_current_quota(actor=outsider, code="requests")
    assert get_quota_status(actor=owner, policy_id=policy.pk).used_units == 0
    assert UsageEvent.objects.filter(policy=policy).count() == 0


def test_consume_replay_conflict_limit_and_immutable_snapshots():
    postgresql_only()
    actor = user("quota-consumer@tests.test")
    policy = grant(actor, limit=3, metadata={"tier": "trial", "revision": 1})
    assert find_current_quota(actor=actor, code="requests").id == policy.id
    first = consume_usage(actor=actor, policy_id=policy.pk, event_key="first", units=2)
    assert (first.used_units, first.remaining_units, first.replayed) == (2, 1, False)
    assert consume_usage(actor=actor, policy_id=policy.pk, event_key="first", units=2).replayed
    with pytest.raises(QuotaConflict):
        consume_usage(actor=actor, policy_id=policy.pk, event_key="first", units=1)
    with pytest.raises(QuotaExceeded):
        consume_usage(actor=actor, policy_id=policy.pk, event_key="too-big", units=2)
    assert (
        consume_usage(actor=actor, policy_id=policy.pk, event_key="last", units=1).remaining_units
        == 0
    )
    with pytest.raises(QuotaExceeded):
        consume_usage(actor=actor, policy_id=policy.pk, event_key="over", units=1)
    counter = UsageCounter.objects.get(policy=policy)
    assert counter.used_units == 3
    assert UsageEvent.objects.filter(policy=policy).count() == 2
    snapshot = UsageEvent.objects.get(policy=policy, event_key="first").policy_snapshot
    assert snapshot["limit_units"] == 3
    assert snapshot["metadata"] == {"tier": "trial", "revision": 1}
    assert snapshot["period_start"] == policy.period_start.isoformat()


def test_expiration_period_boundaries_zero_limit_and_replay_after_close(monkeypatch):
    postgresql_only()
    actor = user("quota-window@tests.test")
    start, end = window()
    expire = start + timedelta(minutes=90)
    policy = provision_quota(
        scope="owner",
        scope_id=actor.pk,
        code="limited",
        period_start=start,
        period_end=end,
        limit_units=1,
        expires_at=expire,
    )
    before_expiry = start + timedelta(minutes=89)
    monkeypatch.setattr("apps.usage_quotas.services.timezone.now", lambda: before_expiry)
    assert consume_usage(actor=actor, policy_id=policy.id, event_key="one").used_units == 1
    monkeypatch.setattr("apps.usage_quotas.services.timezone.now", lambda: expire)
    with pytest.raises(QuotaRuleError):
        consume_usage(actor=actor, policy_id=policy.id, event_key="new")
    assert consume_usage(actor=actor, policy_id=policy.id, event_key="one").replayed
    with pytest.raises(NotFound):
        find_current_quota(actor=actor, code="limited")
    assert UsageEvent.objects.filter(policy=policy).count() == 1
    zero = provision_quota(
        scope="owner",
        scope_id=actor.pk,
        code="disabled",
        period_start=start,
        period_end=end,
        limit_units=0,
    )
    with pytest.raises(QuotaExceeded):
        consume_usage(actor=actor, policy_id=zero.pk, event_key="zero")
    assert UsageCounter.objects.get(policy=zero).used_units == 0


def test_non_overlapping_periods_and_no_implicit_billing_schedule():
    postgresql_only()
    actor = user("quota-period@tests.test")
    start, end = window()
    first = provision_quota(
        scope="owner",
        scope_id=actor.pk,
        code="credits",
        period_start=start,
        period_end=end,
        limit_units=1,
    )
    with pytest.raises(QuotaConflict):
        provision_quota(
            scope="owner",
            scope_id=actor.pk,
            code="credits",
            period_start=end - timedelta(seconds=1),
            period_end=end + timedelta(days=3),
            limit_units=2,
        )
    second = provision_quota(
        scope="owner",
        scope_id=actor.pk,
        code="credits",
        period_start=end,
        period_end=end + timedelta(days=30),
        limit_units=10,
    )
    assert first.id != second.id
    assert UsagePolicy.objects.filter(owner=actor, code="credits").count() == 2


def test_bad_scopes_invalid_identifiers_and_unknown_owners():
    postgresql_only()
    actor = user("quota-validation@tests.test")
    start, end = window()
    for scope, identifier in (
        ("root", actor.pk),
        ("owner", "bogus"),
        ("owner", uuid4()),
        ("tenant", uuid4()),
    ):
        with pytest.raises(QuotaRuleError):
            provision_quota(
                scope=scope,
                scope_id=identifier,
                code="requests",
                period_start=start,
                period_end=end,
                limit_units=5,
            )
