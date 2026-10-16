# ruff: noqa: E402
"""Independent Inventory API, stock correctness, idempotency and negative IDOR tests."""

import pytest
from django.conf import settings

if settings.INVENTORY_MODE != "standalone":
    pytest.skip("Personal Inventory schema not selected", allow_module_level=True)

from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from rest_framework.exceptions import NotFound
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.inventory.models import (
    InventoryItem,
    InventoryOperation,
    StockBalance,
    StockMovement,
    StockReservation,
    Warehouse,
)
from apps.inventory.services import execute_stock_operation
from apps.users.models import User

pytestmark = pytest.mark.django_db


def principal(email, *, superuser=False):
    owner = User.objects.create_user(
        email=email,
        password="long-strong-warehouse-personal-password",
        email_verified=True,
        is_staff=superuser,
        is_superuser=superuser,
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(owner).access_token}")
    return owner, client


@pytest.fixture
def stock():
    actor, client = principal("stock-owner@standalone.test")
    item = client.post(
        reverse("inventory-items-list"), {"sku": "  hammer01 ", "name": "Hammer"}, format="json"
    )
    assert item.status_code == 201, item.data
    source = client.post(
        reverse("inventory-warehouses-list"), {"code": "main", "name": "Main"}, format="json"
    )
    assert source.status_code == 201, source.data
    target = client.post(
        reverse("inventory-warehouses-list"), {"code": "branch", "name": "Branch"}, format="json"
    )
    assert target.status_code == 201, target.data
    return {
        "actor": actor,
        "api": client,
        "item": InventoryItem.objects.get(pk=item.data["id"]),
        "source": Warehouse.objects.get(pk=source.data["id"]),
        "target": Warehouse.objects.get(pk=target.data["id"]),
    }


def command(stock, kind, *, key, quantity=None, source=None, destination=None, reservation=None):
    payload = {"kind": kind, "idempotency_key": key}
    if quantity is not None:
        payload["quantity"] = quantity
    if source is not None:
        payload["warehouse"] = str(source.pk)
        payload["item"] = str(stock["item"].pk)
    if destination is not None:
        payload["destination"] = str(destination.pk)
    if reservation is not None:
        payload["reservation"] = str(reservation)
    return stock["api"].post(reverse("inventory-operations-list"), payload, format="json")


def test_standalone_warehouse_stock_reservations_and_idempotency(stock):
    source = stock["source"]
    assert stock["item"].sku == "HAMMER01"
    first = command(stock, "receive", key="receive-000001", quantity=10, source=source)
    assert first.status_code == 200, first.data
    replay = command(stock, "receive", key="receive-000001", quantity=10, source=source)
    assert replay.status_code == 200 and replay.data == first.data
    assert InventoryOperation.objects.count() == 1
    reserve = command(stock, "reserve", key="reserve-000001", quantity=6, source=source)
    assert reserve.status_code == 200, reserve.data
    held = StockBalance.objects.get(warehouse=source)
    assert held.on_hand == 10 and held.reserved == 6 and held.available == 4
    denied = command(stock, "issue", key="issue-0000001", quantity=5, source=source)
    assert denied.status_code == 400
    assert StockMovement.objects.count() == 2
    release = command(
        stock, "release", key="release-00001", reservation=reserve.data["reservation_id"]
    )
    assert release.status_code == 200, release.data
    closed = StockReservation.objects.get(pk=reserve.data["reservation_id"])
    assert closed.status == "released"
    assert command(stock, "release", key="release-00002", reservation=closed.pk).status_code == 400
    transferred = command(
        stock,
        "transfer",
        key="transfer-0001",
        quantity=3,
        source=source,
        destination=stock["target"],
    )
    assert transferred.status_code == 200, transferred.data
    assert StockBalance.objects.get(warehouse=source).on_hand == 7
    assert StockBalance.objects.get(warehouse=stock["target"]).on_hand == 3
    assert StockMovement.objects.filter(operation_id=transferred.data["operation_id"]).count() == 2
    movement = StockMovement.objects.first()
    with pytest.raises(DjangoValidationError):
        movement.delete()


def test_foreign_stock_is_denied_even_to_global_superuser(stock):
    stranger, other_api = principal("stock-intruder@standalone.test")
    _, root_api = principal("stock-superuser@standalone.test", superuser=True)
    for client in (other_api, root_api):
        assert client.get(reverse("inventory-items-list")).data["count"] == 0
        assert (
            client.get(
                reverse("inventory-warehouses-detail", kwargs={"pk": stock["source"].pk})
            ).status_code
            == 404
        )
        assert (
            client.patch(
                reverse("inventory-warehouses-detail", kwargs={"pk": stock["source"].pk}),
                {"name": "Stolen"},
                format="json",
            ).status_code
            == 404
        )
        assert (
            client.post(
                reverse("inventory-operations-list"),
                {
                    "kind": "receive",
                    "idempotency_key": "intruder-receipt",
                    "warehouse": str(stock["source"].pk),
                    "item": str(stock["item"].pk),
                    "quantity": 10,
                },
                format="json",
            ).status_code
            == 400
        )

    with pytest.raises(NotFound):
        execute_stock_operation(
            actor=stranger,
            data={
                "kind": "receive",
                "idempotency_key": "direct-intruder",
                "warehouse": stock["source"],
                "item": stock["item"],
                "quantity": 10,
            },
        )
    assert not StockBalance.objects.exists()


def test_owner_must_match_foreign_keys_for_direct_model_writes(stock):
    stranger, _ = principal("stock-otherowner@standalone.test")
    with pytest.raises(DjangoValidationError):
        StockBalance.objects.create(
            owner=stranger,
            warehouse=stock["source"],
            item=stock["item"],
        )
    assert not StockBalance.objects.exists()
