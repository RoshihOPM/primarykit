# ruff: noqa: E402
"""Black-box list/detail/write IDOR regressions for the shared tenant adapter."""

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework.test import APIClient

if settings.INVENTORY_MODE != "tenant":
    pytest.skip("Tenant-only policy API tests", allow_module_level=True)

from apps.catalog.models import CatalogItem, Category
from apps.inventory.models import InventoryOperation, Warehouse
from apps.organizations.models import Branch, BranchAccess, Membership, Organization
from apps.users.models import User

pytestmark = pytest.mark.django_db


def api(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def endpoint(organization, name, **kwargs):
    return reverse(name, kwargs={"org_id": organization.pk, **kwargs})


def user(email, *, superuser=False):
    return User.objects.create_user(
        email=email,
        password="long-test-password-123",
        email_verified=True,
        is_staff=superuser,
        is_superuser=superuser,
    )


def test_list_detail_patch_and_stock_commands_are_tenant_and_branch_scoped():
    org = Organization.objects.create(slug="api-policy-a", name="A")
    foreign_org = Organization.objects.create(slug="api-policy-b", name="B")
    manager = user("api-policy-manager@example.test")
    foreign_owner = user("api-policy-owner@example.test")
    membership = Membership.objects.create(
        user=manager, organization=org, role=Membership.Role.MANAGER
    )
    Membership.objects.create(
        user=foreign_owner, organization=foreign_org, role=Membership.Role.OWNER
    )
    allowed_branch = Branch.objects.create(organization=org, code="allowed", name="Allowed")
    blocked_branch = Branch.objects.create(organization=org, code="blocked", name="Blocked")
    foreign_branch = Branch.objects.create(organization=foreign_org, code="foreign", name="Foreign")
    BranchAccess.objects.create(membership=membership, branch=allowed_branch)
    allowed = Warehouse.objects.create(
        organization=org, branch=allowed_branch, code="allowed", name="Allowed"
    )
    blocked = Warehouse.objects.create(
        organization=org, branch=blocked_branch, code="blocked", name="Blocked"
    )
    foreign = Warehouse.objects.create(
        organization=foreign_org, branch=foreign_branch, code="foreign", name="Foreign"
    )
    category = Category.objects.create(organization=org, slug="parts", name="Parts")
    item = CatalogItem.objects.create(
        organization=org, category=category, sku="PART-A", name="Part"
    )
    client = api(manager)
    list_url = endpoint(org, "inventory-warehouses-list")
    assert client.get(list_url).data["count"] == 1
    assert (
        client.get(endpoint(org, "inventory-warehouses-detail", pk=allowed.pk)).status_code == 200
    )
    for hidden in (blocked, foreign):
        detail_url = endpoint(org, "inventory-warehouses-detail", pk=hidden.pk)
        assert client.get(detail_url).status_code == 404
        assert client.patch(detail_url, {"name": "Stolen"}, format="json").status_code == 404

    command_url = endpoint(org, "inventory-operations-list")
    denied = client.post(
        command_url,
        {
            "kind": "receive",
            "idempotency_key": "policy-blocked-001",
            "warehouse": str(blocked.pk),
            "item": str(item.pk),
            "quantity": 1,
        },
        format="json",
    )
    assert denied.status_code == 400
    assert not InventoryOperation.objects.exists()
    allowed_command = client.post(
        command_url,
        {
            "kind": "receive",
            "idempotency_key": "policy-allowed-001",
            "warehouse": str(allowed.pk),
            "item": str(item.pk),
            "quantity": 2,
        },
        format="json",
    )
    assert allowed_command.status_code == 200, allowed_command.data
    assert InventoryOperation.objects.count() == 1

    assert client.get(endpoint(foreign_org, "inventory-warehouses-list")).status_code == 404
    assert client.get(endpoint(org, "catalog-items-detail", pk=item.pk)).status_code == 200
    assert (
        api(foreign_owner)
        .get(endpoint(foreign_org, "catalog-items-detail", pk=item.pk))
        .status_code
        == 404
    )
    membership.is_active = False
    membership.save(update_fields=["is_active"])
    assert client.get(list_url).status_code == 404
    assert (
        client.get(endpoint(org, "inventory-warehouses-detail", pk=allowed.pk)).status_code == 404
    )
    assert client.post(command_url, {}, format="json").status_code == 404


def test_staff_and_superuser_without_membership_have_no_tenant_access():
    org = Organization.objects.create(slug="api-policy-root", name="Root")
    root = user("api-policy-root@example.test", superuser=True)
    client = api(root)
    assert client.get(endpoint(org, "catalog-categories-list")).status_code == 404
    assert client.get(endpoint(org, "inventory-warehouses-list")).status_code == 404
    assert (
        client.post(endpoint(org, "inventory-operations-list"), {}, format="json").status_code
        == 404
    )
