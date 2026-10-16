"""Order snapshots remain private and idempotent with or without other apps."""

import pytest
from rest_framework.exceptions import NotFound
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.orders.domain import OrderRuleViolation, normalize_order_lines
from apps.orders.models import Order, OrderItem
from apps.orders.services import cancel_order, place_order
from apps.users.models import User

pytestmark = pytest.mark.django_db


def client(email, superuser=False):
    user = User.objects.create_user(
        email=email, password="strong-orders-password-67890", email_verified=True,
        is_staff=superuser, is_superuser=superuser,
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return user, api


def payload():
    return {
        "currency": "USD", "idempotency_key": "test-order-0001",
        "lines": [{"sku": "tea", "title": "Tea", "quantity": 2, "unit_price_minor": 125}],
    }


def test_order_create_replay_cancel_and_immutable_snapshot():
    actor, api = client("order-a@example.test")
    response = api.post("/api/v1/orders/", payload(), format="json")
    assert response.status_code == 201, response.data
    assert response.data["total_minor"] == 250
    assert response.data["items"][0]["sku"] == "TEA"
    assert api.post("/api/v1/orders/", payload(), format="json").data["id"] == response.data["id"]
    assert Order.objects.count() == 1
    assert OrderItem.objects.count() == 1
    changed = payload()
    changed["lines"][0]["unit_price_minor"] = 1
    assert api.post("/api/v1/orders/", changed, format="json").status_code == 400
    assert api.post(f"/api/v1/orders/{response.data['id']}/cancel/").status_code == 200
    assert api.post(f"/api/v1/orders/{response.data['id']}/cancel/").status_code == 400
    assert Order.objects.get(pk=response.data["id"]).status == "canceled"
    assert actor.pk == Order.objects.first().owner_id


def test_order_scope_and_direct_service_idor():
    owner, api = client("orders-owner@example.test")
    _, other = client("orders-other@example.test")
    _, root = client("orders-root@example.test", superuser=True)
    order = place_order(actor=owner, **payload())
    for stranger in (other, root):
        assert stranger.get("/api/v1/orders/").data["count"] == 0
        assert stranger.get(f"/api/v1/orders/{order.pk}/").status_code == 404
        assert stranger.post(f"/api/v1/orders/{order.pk}/cancel/").status_code == 404
    actor = User.objects.get(email="orders-other@example.test")
    with pytest.raises(NotFound):
        cancel_order(actor=actor, order_id=order.pk)
    assert api.get(f"/api/v1/orders/{order.pk}/").status_code == 200


def test_orders_reject_invalid_minor_values_and_missing_lines():
    for price in (-1, True, 10**15):
        with pytest.raises(OrderRuleViolation):
            normalize_order_lines("USD", [
                {"sku": "sku", "title": "Name", "quantity": 1, "unit_price_minor": price}
            ])
    with pytest.raises(OrderRuleViolation):
        normalize_order_lines("usd", [])
    _, api = client("orders-invalid@example.test")
    bad = payload()
    bad["lines"][0]["quantity"] = -1
    assert api.post("/api/v1/orders/", bad, format="json").status_code == 400
