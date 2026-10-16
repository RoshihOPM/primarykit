"""Sales are independent records; optional Orders integration validates snapshots."""

import pytest
from django.apps import apps
from rest_framework.exceptions import NotFound
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.sales.models import Sale, SaleLineItem
from apps.sales.services import record_sale, void_sale
from apps.users.models import User

pytestmark = pytest.mark.django_db


def auth(email, superuser=False):
    user = User.objects.create_user(
        email=email, password="strong-sales-password-12345", email_verified=True,
        is_superuser=superuser, is_staff=superuser,
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return user, api


def command():
    return {
        "currency": "KZT",
        "idempotency_key": "sale-record-001",
        "lines": [
            {"sku": "abc", "title": "Tea", "quantity": 3, "unit_price_minor": 150}
        ],
    }


def test_sale_records_snapshot_replays_and_voids():
    owner, api = auth("sales-owner@tests.example")
    response = api.post("/api/v1/sales/", command(), format="json")
    assert response.status_code == 201, response.data
    assert response.data["total_minor"] == 450
    assert response.data["lines"][0]["line_total_minor"] == 450
    assert api.post("/api/v1/sales/", command(), format="json").data["id"] == response.data["id"]
    assert Sale.objects.count() == 1
    assert SaleLineItem.objects.count() == 1
    changed = command()
    changed["lines"][0]["quantity"] = 5
    assert api.post("/api/v1/sales/", changed, format="json").status_code == 400
    assert api.post(f"/api/v1/sales/{response.data['id']}/void/").status_code == 200
    assert api.post(f"/api/v1/sales/{response.data['id']}/void/").status_code == 400
    assert Sale.objects.first().owner_id == owner.pk


def test_sales_cross_owner_and_superuser_are_denied():
    owner, api = auth("sales-owner2@tests.example")
    _, other = auth("sales-other@tests.example")
    _, root = auth("sales-root@tests.example", superuser=True)
    sale = record_sale(actor=owner, **command())
    for attacker in (other, root):
        assert attacker.get("/api/v1/sales/").data["count"] == 0
        assert attacker.get(f"/api/v1/sales/{sale.pk}/").status_code == 404
        assert attacker.post(f"/api/v1/sales/{sale.pk}/void/").status_code == 404
    with pytest.raises(NotFound):
        void_sale(actor=User.objects.get(email="sales-other@tests.example"), sale_id=sale.pk)
    assert api.get(f"/api/v1/sales/{sale.pk}/").status_code == 200


def test_optional_orders_link_cannot_reference_other_users_or_forge_amount():
    if not apps.is_installed("apps.orders"):
        pytest.skip("Orders not installed")
    from apps.orders.services import place_order

    owner, api = auth("sales-integration@tests.example")
    other, _ = auth("sales-integration-other@tests.example")
    order_payload = {
        "currency": "KZT",
        "lines": [{"sku": "abc", "title": "Tea", "quantity": 3, "unit_price_minor": 150}],
        "idempotency_key": "new-order-0001",
    }
    order = place_order(actor=owner, **order_payload)
    foreign = place_order(actor=other, **order_payload)
    data = {**command(), "source_order_id": str(foreign.pk)}
    assert api.post("/api/v1/sales/", data, format="json").status_code == 404
    data["source_order_id"] = str(order.pk)
    data["lines"][0]["unit_price_minor"] = 500
    assert api.post("/api/v1/sales/", data, format="json").status_code == 400
    data = {**command(), "source_order_id": str(order.pk)}
    assert api.post("/api/v1/sales/", data, format="json").status_code == 201
    data["idempotency_key"] = "another-sale0001"
    assert api.post("/api/v1/sales/", data, format="json").status_code == 400
