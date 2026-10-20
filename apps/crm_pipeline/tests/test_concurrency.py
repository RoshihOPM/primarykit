"""Two concurrent Deal transitions cannot duplicate a linked Kanban move."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, connections

from apps.crm_pipeline.models import DealCardLink
from apps.crm_pipeline.tests.test_pipeline import setup_deal_board
from apps.deals.models import Deal
from apps.deals.services import StaleDeal, transition_deal
from apps.kanban.models import CardMove
from apps.users.models import User


@pytest.mark.django_db(transaction=True)
def test_concurrent_deal_transitions_project_once():
    if connection.vendor != "postgresql":
        pytest.skip("Requires real PostgreSQL row locks")
    owner = User.objects.create_user(email="pipeline-race@example.test", password="test-password")
    deal, card, columns = setup_deal_board(owner)
    DealCardLink.objects.create(owner=owner, deal=deal, card=card)
    barrier = Barrier(2)

    def worker(_):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            try:
                transition_deal(
                    actor=owner,
                    deal_id=deal.pk,
                    expected_version=0,
                    stage=Deal.Stage.NEGOTIATION,
                )
                return "moved"
            except StaleDeal:
                return "stale"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(worker, range(2))) == ["moved", "stale"]
    deal.refresh_from_db()
    card.refresh_from_db()
    assert deal.version == 1
    assert card.version == 1
    assert card.column_id == columns[Deal.Stage.NEGOTIATION].pk
    assert CardMove.objects.filter(card=card).count() == 1
