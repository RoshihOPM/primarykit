"""Security and plug-and-play regression suite for read-only statistics."""

from datetime import date, timedelta

import pytest
from django.apps import apps
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.statistics.domain import MetricsValidationError, resolve_period
from apps.statistics.registry import discover_metrics
from apps.users.models import User

pytestmark = pytest.mark.django_db


def identity(email, *, superuser=False):
    user = User.objects.create_user(
        email=email,
        password="robust-statistics-demo-password-1",
        email_verified=True,
        is_superuser=superuser,
        is_staff=superuser,
    )
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}"
    )
    return user, client


def values(response):
    assert response.status_code == 200, getattr(response, "data", None)
    return {row["key"]: row["value"] for row in response.data["metrics"]}


def test_date_preset_domain_validation():
    today = date(2026, 10, 16)
    assert resolve_period(preset="7d", today=today, start=None, end=None).start_date == (
        today - timedelta(days=6)
    )
    assert resolve_period(
        preset="custom", today=today, start="2026-10-01", end="2026-10-07"
    ).end_date == date(2026, 10, 7)
    for kwargs in (
        {"preset": "13d", "start": None, "end": None},
        {"preset": "custom", "start": "2026-10-07", "end": "2026-10-01"},
        {"preset": "custom", "start": "2020-01-01", "end": "2026-10-01"},
        {"preset": "custom", "start": "20261001", "end": "2026-10-07"},
        {"preset": "7d", "start": "2026-10-01", "end": None},
    ):
        with pytest.raises(MetricsValidationError):
            resolve_period(today=today, **kwargs)


def test_statistics_api_is_authenticated_and_filters_system_metrics():
    assert APIClient().get("/api/v1/statistics/").status_code == 401
    _, client = identity("stats-personal@tests.test")
    response = client.get("/api/v1/statistics/available/")
    assert response.status_code == 200, response.data
    found = {m["key"] for m in response.data["metrics"]}
    assert not any(key.startswith("users.") or key.startswith("audit.") for key in found)
    assert client.get("/api/v1/admin/statistics/").status_code == 403
    assert client.get("/api/v1/admin/statistics/available/").status_code == 403
    for invalid in ("unknown", "custom"):
        assert client.get("/api/v1/statistics/", {"period": invalid}).status_code == 400
    assert client.get(
        "/api/v1/statistics/",
        {"period": "custom", "start": "2026-10-04", "end": "2026-10-01"},
    ).status_code == 400


def test_superuser_system_metrics_but_no_private_data():
    _, owner_api = identity("stats-owner@tests.test")
    _, admin_api = identity("stats-superuser@tests.test", superuser=True)
    system = values(admin_api.get("/api/v1/admin/statistics/"))
    assert system["users.total_users"] >= 2
    assert system["users.active_users"] >= 2
    assert "users.total_users" not in values(owner_api.get("/api/v1/statistics/"))
    assert "users.total_users" not in values(admin_api.get("/api/v1/statistics/"))
    assert admin_api.get("/api/v1/admin/statistics/available/").status_code == 200


def test_auto_discovered_providers_match_installed_modules():
    personal = {key for key, _ in discover_metrics("personal")}
    available = {app.label for app in apps.get_app_configs()}
    assert ("storage.files" in personal) == ("storage" in available)
    if "catalog" in available:
        assert ("catalog.items" in personal) == (settings.CATALOG_MODE == "standalone")
    if "inventory" in available:
        assert ("inventory.on_hand" in personal) == (settings.INVENTORY_MODE == "standalone")
    assert "users.total_users" not in personal


def test_personal_catalog_metrics_enforce_owner():
    if not apps.is_installed("apps.catalog") or settings.CATALOG_MODE != "standalone":
        pytest.skip("Standalone catalog not installed")
    from apps.catalog.models import CatalogItem, Category

    owner, owner_api = identity("metric-cat-own@tests.test")
    other, other_api = identity("metric-cat-other@tests.test")
    first = Category.objects.create(owner=owner, slug="mine", name="Mine")
    second = Category.objects.create(owner=other, slug="theirs", name="Theirs")
    CatalogItem.objects.create(owner=owner, category=first, name="Pencil", sku="PEN")
    CatalogItem.objects.create(owner=other, category=second, name="Secret", sku="SECRET")
    assert values(owner_api.get("/api/v1/statistics/"))["catalog.items"] == 1
    assert values(other_api.get("/api/v1/statistics/"))["catalog.items"] == 1
    assert values(owner_api.get("/api/v1/statistics/"))["catalog.categories"] == 1


def test_personal_inventory_metrics_enforce_owner():
    if not apps.is_installed("apps.inventory") or settings.INVENTORY_MODE != "standalone":
        pytest.skip("Standalone inventory not installed")
    from apps.inventory.models import InventoryItem, StockBalance, Warehouse

    owner, owner_api = identity("metric-inv-own@tests.test")
    other, other_api = identity("metric-inv-other@tests.test")
    wh1 = Warehouse.objects.create(owner=owner, code="one", name="One")
    wh2 = Warehouse.objects.create(owner=other, code="two", name="Two")
    item1 = InventoryItem.objects.create(owner=owner, sku="ONE", name="First")
    item2 = InventoryItem.objects.create(owner=other, sku="TWO", name="Second")
    StockBalance.objects.create(owner=owner, warehouse=wh1, item=item1, on_hand=9, reserved=3)
    StockBalance.objects.create(owner=other, warehouse=wh2, item=item2, on_hand=50)
    own = values(owner_api.get("/api/v1/statistics/"))
    assert own["inventory.on_hand"] == 9
    assert own["inventory.reserved"] == 3
    assert own["inventory.warehouses"] == 1
    assert values(other_api.get("/api/v1/statistics/"))["inventory.on_hand"] == 50


def test_private_storage_does_not_include_foreign_or_tenant_files():
    if not apps.is_installed("apps.storage"):
        pytest.skip("Storage not installed")
    from apps.storage.models import StoredFile

    owner, owner_api = identity("metric-storage-own@tests.test")
    other, other_api = identity("metric-storage-other@tests.test")
    common = {"original_name": "image.jpg", "content_type": "image/jpeg", "sha256": "f" * 64}
    StoredFile.objects.create(
        owner=owner, size=17, object_key="private/metrics/owned", **common
    )
    StoredFile.objects.create(
        owner=other, size=1024, object_key="private/metrics/other", **common
    )
    StoredFile.objects.create(
        owner=owner,
        size=2000,
        organization_id="a4b2b1f7-5c69-4b38-8453-596951786699",
        object_key="private/metrics/tenant",
        **common,
    )
    assert values(owner_api.get("/api/v1/statistics/"))["storage.bytes"] == 17
    assert values(other_api.get("/api/v1/statistics/"))["storage.bytes"] == 1024


def test_company_scope_requires_active_owner_or_admin_not_superuser():
    if not apps.is_installed("apps.organizations"):
        pytest.skip("Organizations not installed")
    from apps.organizations.models import Membership, Organization

    company = Organization.objects.create(name="Numbers", slug="numbers")
    second = Organization.objects.create(name="Another", slug="another")
    owner, owner_api = identity("stats-org-owner@tests.test")
    _, member_api = identity("stats-org-member@tests.test")
    member = User.objects.get(email="stats-org-member@tests.test")
    _, stranger_api = identity("stats-org-stranger@tests.test")
    _, superuser_api = identity("stats-org-super@tests.test", superuser=True)
    Membership.objects.create(organization=company, user=owner, role="owner")
    member_link = Membership.objects.create(organization=company, user=member, role="member")
    base = f"/api/v1/organizations/{company.pk}/statistics/"
    assert values(owner_api.get(base))["organizations.members"] == 2
    assert member_api.get(base).status_code == 403
    assert stranger_api.get(base).status_code == 404
    assert superuser_api.get(base).status_code == 404
    assert owner_api.get(
        f"/api/v1/organizations/{second.pk}/statistics/"
    ).status_code == 404
    member_link.is_active = False
    member_link.save(update_fields=["is_active"])
    assert values(owner_api.get(base))["organizations.members"] == 1
    Membership.objects.filter(organization=company, user=owner).update(is_active=False)
    assert owner_api.get(base).status_code == 404


def test_tenant_metrics_are_isolated_by_company():
    if not apps.is_installed("apps.organizations"):
        pytest.skip("Organizations not installed")
    from apps.organizations.models import Membership, Organization

    left = Organization.objects.create(slug="metrics-left", name="Left")
    right = Organization.objects.create(slug="metrics-right", name="Right")
    owner, api = identity("metrics-company-owner@tests.test")
    Membership.objects.create(organization=left, user=owner, role="owner")
    Membership.objects.create(organization=right, user=owner, role="owner")

    if apps.is_installed("apps.catalog") and settings.CATALOG_MODE == "tenant":
        from apps.catalog.models import CatalogItem, Category

        for org, n in ((left, 1), (right, 3)):
            category = Category.objects.create(
                organization=org, name="Parts", slug="parts"
            )
            for i in range(n):
                CatalogItem.objects.create(
                    organization=org, category=category, sku=f"{org.slug}-{i}", name="Part"
                )
        a = values(api.get(f"/api/v1/organizations/{left.pk}/statistics/"))
        b = values(api.get(f"/api/v1/organizations/{right.pk}/statistics/"))
        assert a["catalog.items"] == 1
        assert b["catalog.items"] == 3

    if apps.is_installed("apps.storage"):
        from apps.storage.models import StoredFile

        payload = {"owner": owner, "original_name": "log.pdf",
                   "content_type": "application/pdf", "sha256": "b" * 64}
        StoredFile.objects.create(
            organization_id=left.pk, size=100, object_key="private/metrics/org-left", **payload
        )
        StoredFile.objects.create(
            organization_id=right.pk, size=900, object_key="private/metrics/org-right", **payload
        )
        a = values(api.get(f"/api/v1/organizations/{left.pk}/statistics/"))
        b = values(api.get(f"/api/v1/organizations/{right.pk}/statistics/"))
        assert a["storage.bytes"] == 100 and b["storage.bytes"] == 900
