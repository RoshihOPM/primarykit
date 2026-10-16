"""IDOR, confused-deputy, role and branch isolation regression tests."""

import pytest
from django.urls import reverse
from rest_framework.exceptions import NotFound
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.catalog.models import CatalogItem, Category
from apps.inventory.models import InventoryOperation, StockBalance, Warehouse
from apps.inventory.services import execute_stock_operation
from apps.organizations.models import Branch, BranchAccess, Membership, Organization
from apps.users.models import User

pytestmark = pytest.mark.django_db


def principal(email, org, role):
    user = User.objects.create_user(
        email=email,
        password="Long-test-password-456",
        email_verified=True,
    )
    membership = Membership.objects.create(user=user, organization=org, role=role)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return user, membership, api


def url(org, name, **kw):
    return reverse(name, kwargs={"org_id": org.pk, **kw})


@pytest.fixture
def two_companies():
    a = Organization.objects.create(slug="org-a", name="Org A")
    b = Organization.objects.create(slug="org-b", name="Org B")
    owner_a, _, api_a = principal("owner-a@tenant.test", a, "owner")
    owner_b, _, api_b = principal("owner-b@tenant.test", b, "owner")
    manager, membership, manager_api = principal("manager@tenant.test", a, "manager")
    member, member_m, member_api = principal("member@tenant.test", a, "member")
    branch_a = Branch.objects.create(organization=a, code="first", name="First")
    branch_a2 = Branch.objects.create(organization=a, code="second", name="Second")
    branch_b = Branch.objects.create(organization=b, code="first", name="First")
    BranchAccess.objects.create(membership=membership, branch=branch_a)
    BranchAccess.objects.create(membership=member_m, branch=branch_a)
    cat_a = Category.objects.create(organization=a, slug="same", name="Parts")
    cat_b = Category.objects.create(organization=b, slug="same", name="Parts")
    item_a = CatalogItem.objects.create(organization=a, category=cat_a, sku="SAME", name="Item A")
    item_b = CatalogItem.objects.create(organization=b, category=cat_b, sku="SAME", name="Item B")
    wh_a = Warehouse.objects.create(organization=a, branch=branch_a, code="one", name="One")
    wh_a2 = Warehouse.objects.create(organization=a, branch=branch_a2, code="two", name="Two")
    wh_b = Warehouse.objects.create(organization=b, branch=branch_b, code="one", name="Other")
    return locals()


def test_tenant_reads_reject_foreign_ids_and_global_superuser(two_companies):
    t = two_companies
    assert t["api_a"].get(url(t["a"], "catalog-items-list")).data["count"] == 1
    assert t["api_b"].get(url(t["b"], "catalog-items-list")).data["count"] == 1
    assert t["api_a"].get(url(t["a"], "catalog-items-detail", pk=t["item_b"].pk)).status_code == 404
    assert (
        t["api_a"].get(url(t["a"], "inventory-warehouses-detail", pk=t["wh_b"].pk)).status_code
        == 404
    )
    assert t["api_b"].get(url(t["a"], "inventory-balances-list")).status_code == 404
    assert t["manager_api"].get(url(t["a"], "inventory-warehouses-list")).data["count"] == 1
    assert t["member_api"].get(url(t["a"], "inventory-warehouses-list")).data["count"] == 1
    assert (
        t["member_api"]
        .get(url(t["a"], "inventory-warehouses-detail", pk=t["wh_a2"].pk))
        .status_code
        == 404
    )


def test_transfer_and_item_reassignment_across_organizations_are_rejected(two_companies):
    t = two_companies
    p = {
        "kind": "receive",
        "idempotency_key": "receive-one-00001",
        "warehouse": str(t["wh_a"].pk),
        "item": str(t["item_b"].pk),
        "quantity": 5,
    }
    assert (
        t["api_a"].post(url(t["a"], "inventory-operations-list"), p, format="json").status_code
        == 400
    )
    assert StockBalance.objects.count() == 0
    p["item"] = str(t["item_a"].pk)
    assert (
        t["api_a"].post(url(t["a"], "inventory-operations-list"), p, format="json").status_code
        == 200
    )
    wrong_dest = {
        "kind": "transfer",
        "idempotency_key": "transfer-0000001",
        "warehouse": str(t["wh_a"].pk),
        "destination": str(t["wh_b"].pk),
        "item": str(t["item_a"].pk),
        "quantity": 2,
    }
    assert (
        t["api_a"]
        .post(
            url(t["a"], "inventory-operations-list"),
            wrong_dest,
            format="json",
        )
        .status_code
        == 400
    )
    assert StockBalance.objects.count() == 1
    assert (
        t["api_a"]
        .post(
            url(t["a"], "inventory-warehouses-list"),
            {"code": "foreign", "name": "Foreign", "branch": str(t["branch_b"].pk)},
            format="json",
        )
        .status_code
        == 400
    )


def test_branch_grants_and_member_roles_protect_stock(two_companies):
    t = two_companies
    p = {
        "kind": "receive",
        "idempotency_key": "receive-manager01",
        "warehouse": str(t["wh_a"].pk),
        "item": str(t["item_a"].pk),
        "quantity": 5,
    }
    assert (
        t["manager_api"]
        .post(url(t["a"], "inventory-operations-list"), p, format="json")
        .status_code
        == 200
    )
    p.update(idempotency_key="receive-manager02", warehouse=str(t["wh_a2"].pk))
    assert (
        t["manager_api"]
        .post(url(t["a"], "inventory-operations-list"), p, format="json")
        .status_code
        == 400
    )
    assert (
        t["member_api"].post(url(t["a"], "inventory-operations-list"), p, format="json").status_code
        == 403
    )
    # Even a direct service caller cannot bypass branch permissions.
    with pytest.raises(NotFound):
        execute_stock_operation(
            actor=t["manager"],
            organization=t["a"],
            data={
                "kind": "receive",
                "idempotency_key": "direct-branch-0001",
                "warehouse": t["wh_a2"],
                "item": t["item_a"],
                "quantity": 3,
            },
        )
    assert InventoryOperation.objects.count() == 1


def test_same_idempotency_key_in_two_companies_is_independent(two_companies):
    t = two_companies
    for org, api, wh, item in (
        (t["a"], t["api_a"], t["wh_a"], t["item_a"]),
        (t["b"], t["api_b"], t["wh_b"], t["item_b"]),
    ):
        res = api.post(
            url(org, "inventory-operations-list"),
            {
                "kind": "receive",
                "idempotency_key": "shared-key-000001",
                "warehouse": str(wh.pk),
                "item": str(item.pk),
                "quantity": 3,
            },
            format="json",
        )
        assert res.status_code == 200, res.data
    assert InventoryOperation.objects.count() == 2


def test_revoked_manager_cannot_replay_idempotency(two_companies):
    t = two_companies
    p = {
        "kind": "receive",
        "idempotency_key": "replay-after-revoke",
        "warehouse": str(t["wh_a"].pk),
        "item": str(t["item_a"].pk),
        "quantity": 5,
    }
    assert (
        t["manager_api"]
        .post(url(t["a"], "inventory-operations-list"), p, format="json")
        .status_code
        == 200
    )
    t["membership"].is_active = False
    t["membership"].save(update_fields=["is_active"])
    assert (
        t["manager_api"]
        .post(url(t["a"], "inventory-operations-list"), p, format="json")
        .status_code
        == 404
    )
    assert StockBalance.objects.get(organization=t["a"]).on_hand == 5


def test_existing_reservation_can_be_released_after_warehouse_deactivation(two_companies):
    t = two_companies
    command_url = url(t["a"], "inventory-operations-list")
    receipt = {
        "kind": "receive",
        "idempotency_key": "receipt-old-00001",
        "warehouse": str(t["wh_a"].pk),
        "item": str(t["item_a"].pk),
        "quantity": 8,
    }
    assert t["api_a"].post(command_url, receipt, format="json").status_code == 200
    receipt["kind"] = "reserve"
    receipt["idempotency_key"] = "reserve-old-00001"
    receipt["quantity"] = 4
    reservation = t["api_a"].post(command_url, receipt, format="json")
    assert reservation.status_code == 200
    assert (
        t["api_a"]
        .patch(
            url(t["a"], "inventory-warehouses-detail", pk=t["wh_a"].pk),
            {"is_active": False},
            format="json",
        )
        .status_code
        == 200
    )
    release = t["api_a"].post(
        command_url,
        {
            "kind": "release",
            "idempotency_key": "release-old-00001",
            "reservation": reservation.data["reservation_id"],
        },
        format="json",
    )
    assert release.status_code == 200, release.data
    balance = StockBalance.objects.get(organization=t["a"])
    assert balance.on_hand == 8 and balance.reserved == 0
