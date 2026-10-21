"""CRM stage-column names cannot drift during an authoritative Deal transition."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, connections
from rest_framework.exceptions import ValidationError

from apps.crm_pipeline.models import DealCardLink
from apps.crm_pipeline.tests.test_pipeline import client, setup_deal_board
from apps.deals.models import Deal
from apps.deals.services import transition_deal
from apps.kanban.services import rename_column
from apps.users.models import User


@pytest.mark.django_db
def test_column_rename_is_allowed_only_before_pipeline_binding():
    owner = User.objects.create_user(email="column-guard@example.test", password="secret")
    deal, card, columns = setup_deal_board(owner)
    api = client(owner)
    url = f"/api/v1/kanban/columns/{columns[Deal.Stage.NEGOTIATION].pk}/"
    assert api.patch(url, {"name": "prospecting"}).status_code == 200
    assert api.patch(url, {"name": Deal.Stage.NEGOTIATION}).status_code == 200

    linked = api.post(
        "/api/v1/crm/pipeline/links/",
        {"deal_id": str(deal.pk), "card_id": str(card.pk)},
    )
    assert linked.status_code == 201, linked.data

    blocked = api.patch(url, {"name": "prospecting"})
    assert blocked.status_code == 400
    columns[Deal.Stage.NEGOTIATION].refresh_from_db()
    assert columns[Deal.Stage.NEGOTIATION].name == Deal.Stage.NEGOTIATION

    moved = api.post(
        f"/api/v1/deals/{deal.pk}/transition/",
        {"stage": Deal.Stage.NEGOTIATION, "expected_version": 0},
    )
    assert moved.status_code == 200, moved.data
    card.refresh_from_db()
    assert card.column_id == columns[Deal.Stage.NEGOTIATION].pk


@pytest.mark.django_db(transaction=True)
def test_column_rename_race_cannot_desynchronize_linked_deal():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL board row locks")
    owner = User.objects.create_user(email="column-race@example.test", password="secret")
    deal, card, columns = setup_deal_board(owner)
    DealCardLink.objects.create(owner=owner, deal=deal, card=card)
    barrier = Barrier(2)

    def worker(action):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            if action == "rename":
                try:
                    rename_column(
                        actor=owner,
                        column_id=columns[Deal.Stage.NEGOTIATION].pk,
                        name="prospecting",
                    )
                except ValidationError:
                    return "blocked"
                return "renamed"
            transition_deal(
                actor=owner,
                deal_id=deal.pk,
                expected_version=0,
                stage=Deal.Stage.NEGOTIATION,
            )
            return "moved"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(worker, ("rename", "transition"))) == ["blocked", "moved"]

    deal.refresh_from_db()
    card.refresh_from_db()
    columns[Deal.Stage.NEGOTIATION].refresh_from_db()
    assert deal.stage == Deal.Stage.NEGOTIATION
    assert card.column_id == columns[Deal.Stage.NEGOTIATION].pk
    assert columns[Deal.Stage.NEGOTIATION].name == Deal.Stage.NEGOTIATION
