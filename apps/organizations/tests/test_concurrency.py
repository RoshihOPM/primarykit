"""PostgreSQL regression for last-owner safety under simultaneous requests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, connections
from rest_framework.exceptions import ValidationError

from apps.organizations.models import Membership, Organization
from apps.organizations.services import update_membership
from apps.users.models import User


@pytest.mark.django_db(transaction=True)
def test_concurrent_owner_demotions_cannot_leave_company_ownerless():
    if connection.vendor != "postgresql":
        pytest.skip("Requires real PostgreSQL row locking")
    first = User.objects.create_user(
        email="owner-one@concurrent.test",
        password="Long-test-password-887",
        email_verified=True,
    )
    second = User.objects.create_user(
        email="owner-two@concurrent.test",
        password="Long-test-password-888",
        email_verified=True,
    )
    org = Organization.objects.create(name="Test", slug="test-concurrent")
    a = Membership.objects.create(organization=org, user=first, role="owner")
    b = Membership.objects.create(organization=org, user=second, role="owner")
    barrier = Barrier(2)

    def attempt(actor, member_id):
        close_old_connections()
        barrier.wait(timeout=10)
        try:
            update_membership(
                actor=actor,
                organization=org,
                membership_id=member_id,
                new_role="member",
            )
            return "changed"
        except ValidationError:
            return "rejected"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(attempt, first, a.pk),
            pool.submit(attempt, second, b.pk),
        ]
        outcomes = [future.result() for future in futures]
    assert sorted(outcomes) == ["changed", "rejected"]
    assert (
        Membership.objects.filter(
            organization=org, role=Membership.Role.OWNER, is_active=True
        ).count()
        == 1
    )
