"""Real PostgreSQL races and negative tenant authorization regression."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from django.apps import apps
from django.db import close_old_connections, connection, connections
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.usage_quotas.domain import QuotaConflict, QuotaExceeded, QuotaRuleError
from apps.usage_quotas.models import UsageCounter, UsageEvent
from apps.usage_quotas.services import consume_usage, get_quota_status, provision_quota
from apps.users.models import User


def only_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL transactions and row locking")


def member(email):
    return User.objects.create_user(email=email, password="Long-password-98", email_verified=True)


def period():
    now = timezone.now()
    return now - timedelta(minutes=5), now + timedelta(hours=1)


@pytest.mark.django_db(transaction=True)
def test_simultaneous_consumption_cannot_overspend():
    only_postgres()
    actor = member("quota-racer@tests.test")
    start, end = period()
    policy = provision_quota(
        scope="owner",
        scope_id=actor.pk,
        code="jobs",
        period_start=start,
        period_end=end,
        limit_units=1,
    )
    barrier = Barrier(2)

    def attempt(index):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            try:
                consume_usage(actor=actor, policy_id=policy.pk, event_key=f"job-{index}")
                return "ok"
            except QuotaExceeded:
                return "limited"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, range(2)))
    assert sorted(outcomes) == ["limited", "ok"]
    assert UsageCounter.objects.get(policy=policy).used_units == 1
    assert UsageEvent.objects.filter(policy=policy).count() == 1


@pytest.mark.django_db(transaction=True)
def test_simultaneous_duplicate_event_returns_one_replay():
    only_postgres()
    actor = member("quota-replay-racer@tests.test")
    start, end = period()
    policy = provision_quota(
        scope="owner",
        scope_id=actor.pk,
        code="jobs",
        period_start=start,
        period_end=end,
        limit_units=3,
    )
    barrier = Barrier(2)

    def attempt(_):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            return consume_usage(actor=actor, policy_id=policy.pk, event_key="one", units=2)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, range(2)))
    assert sorted(result.replayed for result in results) == [False, True]
    assert [result.used_units for result in results] == [2, 2]
    assert UsageCounter.objects.get(policy=policy).used_units == 2
    assert UsageEvent.objects.filter(policy=policy).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_provisioning_rejects_overlapping_windows():
    only_postgres()
    actor = member("quota-provision-racer@tests.test")
    start, end = period()
    barrier = Barrier(2)

    def attempt(_):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            try:
                provision_quota(
                    scope="owner",
                    scope_id=actor.pk,
                    code="jobs",
                    period_start=start,
                    period_end=end,
                    limit_units=4,
                )
                return "ok"
            except QuotaConflict:
                return "overlap"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, range(2)))
    assert sorted(outcomes) == ["ok", "overlap"]


@pytest.mark.django_db
def test_tenant_scope_membership_and_deactivation_idor():
    only_postgres()
    if not apps.is_installed("apps.organizations"):
        pytest.skip("Tenant adapter is optional")
    from apps.organizations.models import Membership, Organization

    owner = member("quota-tenant-owner@tests.test")
    outsider = member("quota-tenant-outsider@tests.test")
    superuser = member("quota-tenant-global@tests.test")
    superuser.is_superuser = True
    superuser.save(update_fields=["is_superuser"])
    organization = Organization.objects.create(slug="usage-sample", name="Usage Sample")
    other = Organization.objects.create(slug="usage-other", name="Other")
    Membership.objects.create(organization=organization, user=owner, role="owner")
    Membership.objects.create(organization=other, user=outsider, role="owner")
    start, end = period()
    policy = provision_quota(
        scope="tenant",
        scope_id=organization.pk,
        code="exports",
        period_start=start,
        period_end=end,
        limit_units=4,
    )
    for actor in (outsider, superuser):
        with pytest.raises(NotFound):
            consume_usage(actor=actor, policy_id=policy.id, event_key="steal")
        with pytest.raises(NotFound):
            get_quota_status(actor=actor, policy_id=policy.id)
    assert (
        consume_usage(actor=owner, policy_id=policy.id, event_key="own", units=2).remaining_units
        == 2
    )
    membership = Membership.objects.get(organization=organization, user=owner)
    membership.is_active = False
    membership.save(update_fields=["is_active"])
    with pytest.raises(NotFound):
        consume_usage(actor=owner, policy_id=policy.id, event_key="after-removal")
    assert UsageCounter.objects.get(policy=policy).used_units == 2
    with pytest.raises(QuotaRuleError):
        provision_quota(
            scope="tenant",
            scope_id=uuid4(),
            code="exports",
            period_start=start,
            period_end=end,
            limit_units=1,
        )
