"""Contract: Deal owns stage; mapped Kanban card is an atomic projection."""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.crm_pipeline.models import DealCardLink
from apps.deals.models import Deal
from apps.kanban.models import Board, Card, CardMove, Column
from apps.users.models import User

pytestmark = pytest.mark.django_db


def setup_deal_board(owner):
    board = Board.objects.create(owner=owner, name="Deals")
    columns = {
        stage: Column.objects.create(board=board, name=stage, position=i)
        for i, stage in enumerate(Deal.Stage.values)
    }
    deal = Deal.objects.create(owner=owner, title="Opportunity")
    card = Card.objects.create(board=board, column=columns[Deal.Stage.OPEN], title="Opportunity")
    return deal, card, columns


def client(user):
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return api


def test_binding_and_transition_are_owner_scoped_and_atomic():
    owner = User.objects.create_user(
        email="pipeline-owner@example.test", password="test-password", email_verified=True
    )
    other = User.objects.create_user(
        email="pipeline-other@example.test", password="test-password", email_verified=True
    )
    api = client(owner)
    intruder = client(other)
    deal, card, columns = setup_deal_board(owner)
    root = "/api/v1/crm/pipeline/links/"
    payload = {"deal_id": str(deal.pk), "card_id": str(card.pk)}
    assert APIClient().get(root).status_code in (401, 403)
    assert intruder.post(root, payload).status_code == 404
    created = api.post(root, payload)
    assert created.status_code == 201, created.data
    assert api.post(root, payload).status_code == 409
    link_id = created.data["id"]
    assert intruder.get(root).data["count"] == 0
    assert intruder.get(root + link_id + "/").status_code == 404
    assert DealCardLink.objects.count() == 1

    # A Kanban card cannot bypass the Deal's authoritative stage.
    blocked = api.post(
        f"/api/v1/kanban/cards/{card.pk}/move/",
        {"target_column_id": str(columns[Deal.Stage.NEGOTIATION].pk), "expected_version": 0},
    )
    assert blocked.status_code == 400
    moved = api.post(
        f"/api/v1/deals/{deal.pk}/transition/",
        {"stage": Deal.Stage.NEGOTIATION, "expected_version": 0},
    )
    assert moved.status_code == 200, moved.data
    card.refresh_from_db()
    assert card.column_id == columns[Deal.Stage.NEGOTIATION].pk
    assert card.version == 1
    assert CardMove.objects.filter(card=card).count() == 1

    # Broken client column configuration never commits a partial stage change.
    columns[Deal.Stage.WON].name = "renamed"
    columns[Deal.Stage.WON].save(update_fields=["name"])
    failed = api.post(
        f"/api/v1/deals/{deal.pk}/transition/",
        {"stage": Deal.Stage.WON, "expected_version": 1},
    )
    assert failed.status_code == 400
    deal.refresh_from_db()
    card.refresh_from_db()
    assert deal.stage == Deal.Stage.NEGOTIATION
    assert deal.version == 1
    assert card.version == 1


def test_cannot_bind_cross_owner_or_incomplete_board():
    owner = User.objects.create_user(
        email="pipeline-owner2@example.test", password="test-password", email_verified=True
    )
    stranger = User.objects.create_user(
        email="pipeline-stranger2@example.test", password="test-password"
    )
    deal, card, columns = setup_deal_board(owner)
    foreign_deal = Deal.objects.create(owner=stranger, title="Foreign")
    api = client(owner)
    root = "/api/v1/crm/pipeline/links/"
    assert (
        api.post(root, {"deal_id": str(foreign_deal.pk), "card_id": str(card.pk)}).status_code
        == 404
    )
    columns[Deal.Stage.WON].name = "missing"
    columns[Deal.Stage.WON].save(update_fields=["name"])
    assert api.post(root, {"deal_id": str(deal.pk), "card_id": str(card.pk)}).status_code == 400
    assert DealCardLink.objects.count() == 0
