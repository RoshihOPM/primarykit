# ruff: noqa: E402
"""Standalone personal Catalog tests, including cross-owner protection."""

import pytest
from django.conf import settings

if settings.CATALOG_MODE != "standalone":
    pytest.skip("Personal Catalog schema not selected", allow_module_level=True)

from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.catalog.models import AttributeDefinition, CatalogItem, Category
from apps.users.models import User

pytestmark = pytest.mark.django_db


def principal(email, *, superuser=False):
    owner = User.objects.create_user(
        email=email,
        password="long-strong-personal-catalog-password",
        email_verified=True,
        is_staff=superuser,
        is_superuser=superuser,
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(owner).access_token}")
    return owner, api


def test_catalog_copy_has_owner_scoped_category_attributes_items_and_idor():
    owner, client = principal("catalog-owner@standalone.test")
    _, stranger = principal("catalog-other@standalone.test")
    _, root = principal("catalog-root@standalone.test", superuser=True)
    category = client.post(
        reverse("catalog-categories-list"), {"slug": "cars", "name": "Cars"}, format="json"
    )
    assert category.status_code == 201, category.data
    obj = Category.objects.get(pk=category.data["id"])
    assert obj.owner == owner
    spec = client.post(
        reverse("catalog-attributes-list"),
        {"category": str(obj.pk), "code": "year", "data_type": "integer", "required": True},
        format="json",
    )
    assert spec.status_code == 201, spec.data
    assert AttributeDefinition.objects.filter(category=obj).exists()
    item = client.post(
        reverse("catalog-items-list"),
        {"category": str(obj.pk), "sku": " car-001 ", "name": "Car", "attributes": {"year": 2026}},
        format="json",
    )
    assert item.status_code == 201, item.data
    product = CatalogItem.objects.get(pk=item.data["id"])
    assert product.owner == owner
    assert product.sku == "CAR-001"
    assert client.get(reverse("catalog-items-list")).data["count"] == 1
    for unauthorized in (stranger, root):
        assert unauthorized.get(reverse("catalog-items-list")).data["count"] == 0
        assert (
            unauthorized.get(reverse("catalog-items-detail", kwargs={"pk": product.pk})).status_code
            == 404
        )
        assert (
            unauthorized.patch(
                reverse("catalog-items-detail", kwargs={"pk": product.pk}), {"name": "Stolen"}
            ).status_code
            == 404
        )


def test_personal_catalog_rejects_foreign_category_and_invalid_attributes():
    owner, api = principal("owner-a@standalone.test")
    other, other_api = principal("owner-b@standalone.test")
    cat = Category.objects.create(owner=other, slug="other", name="Other")
    response = api.post(
        reverse("catalog-items-list"),
        {"category": str(cat.pk), "sku": "S1", "name": "Bad"},
        format="json",
    )
    assert response.status_code == 400
    local = Category.objects.create(owner=owner, slug="main", name="Main")
    AttributeDefinition.objects.create(
        category=local, code="weight", data_type="integer", required=True
    )
    missing = api.post(
        reverse("catalog-items-list"),
        {"category": str(local.pk), "sku": "S1", "name": "Bad", "attributes": {}},
        format="json",
    )
    assert missing.status_code == 400
    valid = api.post(
        reverse("catalog-items-list"),
        {"category": str(local.pk), "sku": "S1", "name": "Good", "attributes": {"weight": 2}},
        format="json",
    )
    assert valid.status_code == 201, valid.data
    assert (
        api.post(
            reverse("catalog-items-list"),
            {
                "category": str(local.pk),
                "sku": "s1",
                "name": "Duplicate",
                "attributes": {"weight": 2},
            },
            format="json",
        ).status_code
        == 400
    )
    with pytest.raises(DjangoValidationError):
        CatalogItem.objects.create(owner=other, category=local, sku="BAD", name="Bad")
    assert other_api.get(reverse("catalog-categories-list")).data["count"] == 1
    assert api.get(reverse("catalog-categories-list")).data["count"] == 1
