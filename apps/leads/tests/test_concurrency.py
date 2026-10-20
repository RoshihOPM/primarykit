"""PostgreSQL race checks for owner-scoped, optimistic lifecycle transitions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, connections

from apps.leads.models import Lead
from apps.leads.services import StaleLead, transition_lead
from apps.users.models import User


@pytest.mark.django_db(transaction=True)
def test_concurrent_transitions_have_one_winner():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    owner = User.objects.create_user(email="leads-race@example.test", password="test-password")
    instance = Lead.objects.create(
        owner=owner, title="Concurrent transition", contact_name="Customer"
    )
    barrier = Barrier(2)

    def transition(_index):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            try:
                transition_lead(
                    actor=owner,
                    lead_id=instance.pk,
                    expected_version=0,
                    status=Lead.Status.QUALIFIED,
                )
                return "moved"
            except StaleLead:
                return "stale"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(transition, range(2)))
    assert sorted(outcomes) == ["moved", "stale"]
    instance.refresh_from_db()
    assert instance.version == 1
    assert instance.status == Lead.Status.QUALIFIED
