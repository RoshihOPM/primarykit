import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.catalog.models import AttributeDefinition, CatalogItem, Category
from apps.users.models import User

pytestmark = pytest.mark.django_db


def api(email, *, admin=False):
    user = User.objects.create_user(
        email=email, password="A-strong-test-password-100", email_verified=True,
        is_staff=admin, is_superuser=admin,
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def test_admin_catalog_and_typed_attributes():
    manager = api("admin@catalog.test", admin=True)
    category = manager.post(
        reverse("catalog-categories-list"), {"slug": "cars", "name": "Cars"}, format="json"
    )
    assert category.status_code == 201, category.data
    cid = category.data["id"]
    for code, kind, required in (
        ("vin", "text", True), ("year", "integer", True),
        ("electric", "boolean", False), ("price", "decimal", False),
    ):
        response = manager.post(
            reverse("catalog-attributes-list"),
            {"category": cid, "code": code, "data_type": kind, "required": required},
            format="json",
        )
        assert response.status_code == 201, response.data
    item = manager.post(
        reverse("catalog-items-list"),
        {
            "sku": " car-001 ", "name": "Car", "category": cid,
            "attributes": {"vin": " A123 ", "year": 2020, "electric": False, "price": "2.50"},
        },
        format="json",
    )
    assert item.status_code == 201, item.data
    saved = CatalogItem.objects.get()
    assert saved.sku == "CAR-001"
    assert saved.attributes == {
        "vin": "A123", "year": 2020, "electric": False, "price": "2.50",
    }
    assert manager.get(reverse("catalog-items-list"), {"category": "cars"}).data["count"] == 1


def test_reject_unknown_missing_or_incorrect_attributes():
    manager = api("manager@catalog.test", admin=True)
    cat = Category.objects.create(slug="products", name="Products")
    AttributeDefinition.objects.create(category=cat, code="weight", data_type="integer", required=True)
    url = reverse("catalog-items-list")
    for attrs in ({}, {"unknown": 2, "weight": 2}, {"weight": True}, {"weight": "2"}):
        response = manager.post(
            url, {"category": str(cat.pk), "sku": "A1", "name": "Test", "attributes": attrs},
            format="json",
        )
        assert response.status_code == 400, response.data
    valid = manager.post(
        url, {"category": str(cat.pk), "sku": "A1", "name": "Test", "attributes": {"weight": 2}},
        format="json",
    )
    assert valid.status_code == 201
    invalid_patch = manager.patch(
        reverse("catalog-items-detail", kwargs={"pk": valid.data["id"]}),
        {"attributes": {"weight": False}},
        format="json",
    )
    assert invalid_patch.status_code == 400
    assert CatalogItem.objects.get().attributes["weight"] == 2


def test_regular_users_cannot_write_or_see_inactive_catalog():
    admin = api("admin@catalog.test", admin=True)
    viewer = api("viewer@catalog.test")
    category = Category.objects.create(slug="secret", name="Secret", is_active=False)
    item = CatalogItem.objects.create(category=category, sku="X01", name="Hidden")
    assert viewer.get(reverse("catalog-items-list")).data["count"] == 0
    assert viewer.get(reverse("catalog-items-detail", kwargs={"pk": item.pk})).status_code == 404
    assert viewer.post(reverse("catalog-items-list"), {"name": "bad"}).status_code == 403
    assert viewer.patch(
        reverse("catalog-items-detail", kwargs={"pk": item.pk}), {"name": "hacked"},
    ).status_code == 403
    assert viewer.get(reverse("catalog-categories-list")).data["count"] == 0
    assert admin.get(reverse("catalog-items-detail", kwargs={"pk": item.pk})).status_code == 200


def test_sku_case_insensitive_uniqueness_and_privilege_fields():
    admin = api("admin@catalog.test", admin=True)
    category = Category.objects.create(slug="books", name="Books")
    url = reverse("catalog-items-list")
    result = admin.post(
        url,
        {"category": str(category.pk), "sku": "book1", "name": "First", "owner_id": "victim"},
        format="json",
    )
    assert result.status_code == 201
    second = admin.post(
        url, {"category": str(category.pk), "sku": "BOOK1", "name": "Second"}, format="json",
    )
    assert second.status_code == 400
    assert CatalogItem.objects.count() == 1
    assert "owner_id" not in result.data
