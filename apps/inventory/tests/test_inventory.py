import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse as django_reverse

from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.catalog.models import CatalogItem, Category
from apps.inventory.models import (
    InventoryOperation,
    StockBalance,
    StockMovement,
    StockReservation,
    Warehouse,
)
from apps.organizations.models import Branch, Membership, Organization
from apps.users.models import User

pytestmark = pytest.mark.django_db


def tenant():
    return Organization.objects.get_or_create(
        slug="inventory-company", defaults={"name": "Inventory company"}
    )[0]


def reverse(name, kwargs=None):
    if name.startswith("inventory-"):
        kwargs = {**(kwargs or {}), "org_id": tenant().pk}
    return django_reverse(name, kwargs=kwargs)


def identity(email, *, admin=False):
    member = User.objects.create_user(
        email=email,
        password="Inventory-long-password-312",
        email_verified=True,
        is_staff=admin,
        is_superuser=admin,
    )
    Membership.objects.create(
        user=member, organization=tenant(), role="owner" if admin else "member"
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member).access_token}")
    return member, api


@pytest.fixture
def stock():
    org = tenant()
    category = Category.objects.create(organization=org, slug="tools", name="Tools")
    item = CatalogItem.objects.create(organization=org, category=category, sku="HAMMER-01", name="Hammer")
    branch = Branch.objects.create(organization=org, code="primary", name="Primary")
    source = Warehouse.objects.create(organization=org, branch=branch, code="main", name="Main")
    destination = Warehouse.objects.create(organization=org, branch=branch, code="branch", name="Branch")
    admin, client = identity("inventory-admin@example.com", admin=True)
    return {
        "item": item,
        "source": source,
        "destination": destination,
        "admin": admin,
        "api": client,
    }


def command(stock, kind, *, key, quantity=None, warehouse=None, destination=None, reservation=None):
    payload = {"kind": kind, "idempotency_key": key}
    if quantity is not None:
        payload["quantity"] = quantity
    if warehouse is not None:
        payload["warehouse"] = str(warehouse.pk)
        payload["item"] = str(stock["item"].pk)
    if destination is not None:
        payload["destination"] = str(destination.pk)
    if reservation is not None:
        payload["reservation"] = str(reservation)
    return stock["api"].post(reverse("inventory-operations-list"), payload, format="json")


def balance(warehouse):
    return StockBalance.objects.get(warehouse=warehouse)


def test_receive_and_issue_cannot_overdraw(stock):
    warehouse = stock["source"]
    received = command(stock, "receive", key="receive-0001", quantity=10, warehouse=warehouse)
    assert received.status_code == 200, received.data
    assert balance(warehouse).on_hand == 10
    assert (
        command(stock, "issue", key="issue-00001", quantity=7, warehouse=warehouse).status_code
        == 200
    )
    failed = command(stock, "issue", key="issue-00002", quantity=4, warehouse=warehouse)
    assert failed.status_code == 400, failed.data
    assert balance(warehouse).on_hand == 3
    assert InventoryOperation.objects.count() == 2
    assert StockMovement.objects.count() == 2


def test_reserve_release_consume_and_no_double_close(stock):
    source = stock["source"]
    command(stock, "receive", key="receive-0001", quantity=10, warehouse=source)
    held = command(stock, "reserve", key="reserve-0001", quantity=6, warehouse=source)
    assert held.status_code == 200
    reservation_id = held.data["reservation_id"]
    balance(source).refresh_from_db()
    assert balance(source).on_hand == 10
    assert balance(source).reserved == 6
    assert balance(source).available == 4
    assert (
        command(stock, "issue", key="issue-00001", quantity=5, warehouse=source).status_code == 400
    )
    consumed = command(stock, "consume", key="consume-0001", reservation=reservation_id)
    assert consumed.status_code == 200, consumed.data
    assert balance(source).on_hand == 4
    assert balance(source).reserved == 0
    assert StockReservation.objects.get(pk=reservation_id).status == "consumed"
    assert (
        command(stock, "consume", key="consume-0002", reservation=reservation_id).status_code == 400
    )
    release_attempt = command(stock, "release", key="release-0001", reservation=reservation_id)
    assert release_attempt.status_code == 400
    held = command(stock, "reserve", key="reserve-0002", quantity=2, warehouse=source)
    assert (
        command(
            stock, "release", key="release-0002", reservation=held.data["reservation_id"]
        ).status_code
        == 200
    )
    assert balance(source).on_hand == 4
    assert balance(source).reserved == 0


def test_transfer_creates_two_ledger_movements(stock):
    source, dest = stock["source"], stock["destination"]
    command(stock, "receive", key="receive-0001", quantity=12, warehouse=source)
    transferred = command(
        stock,
        "transfer",
        key="transfer-0001",
        quantity=5,
        warehouse=source,
        destination=dest,
    )
    assert transferred.status_code == 200, transferred.data
    assert balance(source).on_hand == 7
    assert balance(dest).on_hand == 5
    movement_rows = StockMovement.objects.filter(operation_id=transferred.data["operation_id"])
    assert movement_rows.count() == 2
    assert set(movement_rows.values_list("on_hand_delta", flat=True)) == {-5, 5}
    assert (
        command(
            stock,
            "transfer",
            key="transfer-0002",
            quantity=8,
            warehouse=source,
            destination=dest,
        ).status_code
        == 400
    )
    assert balance(dest).on_hand == 5


def test_idempotent_retries_do_not_duplicate_or_change_state(stock):
    source = stock["source"]
    first = command(stock, "receive", key="receive-0001", quantity=10, warehouse=source)
    second = command(stock, "receive", key="receive-0001", quantity=10, warehouse=source)
    assert first.status_code == second.status_code == 200
    assert first.data == second.data
    assert balance(source).on_hand == 10
    assert InventoryOperation.objects.count() == 1
    assert StockMovement.objects.count() == 1
    collision = command(stock, "receive", key="receive-0001", quantity=11, warehouse=source)
    assert collision.status_code == 400
    assert balance(source).on_hand == 10


def test_invalid_operation_shapes_and_over_reserved(stock):
    source = stock["source"]
    url = reverse("inventory-operations-list")
    api = stock["api"]
    assert (
        api.post(
            url, {"kind": "receive", "idempotency_key": "missing-0001"}, format="json"
        ).status_code
        == 400
    )
    assert (
        command(stock, "issue", key="issue-00001", quantity=1, warehouse=source).status_code == 400
    )
    assert (
        command(
            stock,
            "transfer",
            key="transfer-0001",
            quantity=1,
            warehouse=source,
            destination=source,
        ).status_code
        == 400
    )
    command(stock, "receive", key="receive-0001", quantity=2, warehouse=source)
    assert (
        command(stock, "reserve", key="reserve-0001", quantity=3, warehouse=source).status_code
        == 400
    )
    assert StockReservation.objects.count() == 0


def test_non_admin_denied_every_inventory_endpoint(stock):
    _, viewer = identity("warehouse-viewer@example.com")
    for name in ("inventory-warehouses-list", "inventory-balances-list"):
        assert viewer.get(reverse(name)).status_code == 200
    for name in ("inventory-reservations-list", "inventory-operations-list"):
        assert viewer.get(reverse(name)).status_code == 403
    assert (
        viewer.post(
            reverse("inventory-operations-list"),
            {"kind": "receive", "idempotency_key": "evil-00001", "quantity": 100},
            format="json",
        ).status_code
        == 403
    )


def test_warehouse_and_ledger_cannot_be_mutated_by_api(stock):
    api = stock["api"]
    created = api.post(
        reverse("inventory-warehouses-list"),
        {"code": "new", "name": "New", "branch": str(stock["source"].branch_id)},
        format="json",
    )
    assert created.status_code == 201
    assert (
        api.patch(
            reverse("inventory-warehouses-detail", kwargs={"pk": created.data["id"]}),
            {"name": "Changed"},
            format="json",
        ).status_code
        == 200
    )
    command(stock, "receive", key="receive-0001", quantity=10, warehouse=stock["source"])
    stored = StockMovement.objects.first()
    with pytest.raises(DjangoValidationError):
        stored.delete()
    with pytest.raises(DjangoValidationError):
        stored.on_hand_delta = 111
        stored.save()
    with pytest.raises(DjangoValidationError):
        StockMovement.objects.all().update(on_hand_delta=222)
    assert (
        api.patch(
            reverse("inventory-balances-detail", kwargs={"pk": balance(stock["source"]).pk}),
            {"on_hand": 1000},
            format="json",
        ).status_code
        == 405
    )
