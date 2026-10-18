"""Public/private visibility, no superuser bypass, moderation and stale writes."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, connections
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.listings.domain import ListingRuleError, next_status, normalize_fields
from apps.listings.models import Listing, ListingCategory
from apps.listings.services import StaleListing, edit_listing, transition_listing
from apps.users.models import User

pytestmark = pytest.mark.django_db


def user_client(email, *, superuser=False):
    user = User.objects.create_user(
        email=email,
        password="secure-listings-test-password",
        email_verified=True,
        is_staff=superuser,
        is_superuser=superuser,
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return user, api


def payload(category):
    return {
        "category": str(category.pk),
        "title": "Used laptop",
        "description": "In good working condition",
        "location_label": "Almaty",
        "price_minor": 120000,
        "currency": "KZT",
        "attributes": {"year": 2022, "warranty": False},
    }


def test_listing_lifecycle_public_visibility_and_private_drafts():
    category = ListingCategory.objects.create(slug="electronics", title="Electronics")
    seller, api = user_client("seller-listings@example.test")
    _, stranger = user_client("stranger-listings@example.test")
    _, moderator = user_client("moderator-listings@example.test", superuser=True)
    public = APIClient()
    created = api.post("/api/v1/listings/", payload(category), format="json")
    assert created.status_code == 201, created.data
    listing_id = created.data["id"]
    assert created.data["status"] == "draft"
    assert public.get("/api/v1/listings/").data["count"] == 0
    assert public.get(f"/api/v1/listings/{listing_id}/").status_code == 404
    assert stranger.get(f"/api/v1/listings/{listing_id}/").status_code == 404
    assert moderator.get(f"/api/v1/listings/{listing_id}/").status_code == 404
    assert api.get("/api/v1/listings/mine/").data["count"] == 1
    assert stranger.get("/api/v1/listings/mine/").data["count"] == 0
    assert public.get("/api/v1/listings/categories/").data[0]["slug"] == "electronics"

    submitted = api.post(
        f"/api/v1/listings/{listing_id}/submit/", {"expected_version": 0}, format="json"
    )
    assert submitted.status_code == 200
    assert submitted.data["version"] == 1
    assert moderator.get("/api/v1/listings/pending/").data["count"] == 1
    assert stranger.get("/api/v1/listings/pending/").status_code == 403
    assert seller.pk == Listing.objects.get(pk=listing_id).owner_id
    assert (
        api.post(
            f"/api/v1/listings/{listing_id}/moderate/",
            {"expected_version": 1, "decision": "approve"},
            format="json",
        ).status_code
        == 403
    )
    approved = moderator.post(
        f"/api/v1/listings/{listing_id}/moderate/",
        {"expected_version": 1, "decision": "approve"},
        format="json",
    )
    assert approved.status_code == 200, approved.data
    assert approved.data["status"] == "published"
    assert public.get("/api/v1/listings/").data["count"] == 1
    assert public.get(f"/api/v1/listings/{listing_id}/").status_code == 200
    assert (
        stranger.patch(
            f"/api/v1/listings/{listing_id}/",
            {"expected_version": 2, "title": "Hacked"},
            format="json",
        ).status_code
        == 404
    )
    assert (
        api.patch(
            f"/api/v1/listings/{listing_id}/",
            {"expected_version": 2, "title": "Changed"},
            format="json",
        ).status_code
        == 400
    )
    assert (
        api.post(
            f"/api/v1/listings/{listing_id}/mark-sold/",
            {"expected_version": 2},
            format="json",
        ).data["status"]
        == "sold"
    )
    assert public.get("/api/v1/listings/").data["count"] == 0
    assert public.get(f"/api/v1/listings/{listing_id}/").status_code == 404


def test_edit_rejects_owner_idor_stale_versions_and_invalid_payloads():
    category = ListingCategory.objects.create(slug="cars", title="Cars")
    owner, api = user_client("owner-ads@example.test")
    intruder, other_api = user_client("intruder-ads@example.test")
    listing_id = api.post("/api/v1/listings/", payload(category), format="json").data["id"]
    assert (
        other_api.patch(
            f"/api/v1/listings/{listing_id}/",
            {"expected_version": 0, "price_minor": 1},
            format="json",
        ).status_code
        == 404
    )
    edited = api.patch(
        f"/api/v1/listings/{listing_id}/",
        {"expected_version": 0, "price_minor": 140000},
        format="json",
    )
    assert edited.status_code == 200
    assert edited.data["version"] == 1
    assert (
        api.patch(
            f"/api/v1/listings/{listing_id}/",
            {"expected_version": 0, "price_minor": 100000},
            format="json",
        ).status_code
        == 409
    )
    with pytest.raises(StaleListing):
        edit_listing(
            actor=owner, listing_id=listing_id, expected_version=0, changes={"title": "abc"}
        )
    from rest_framework.exceptions import NotFound

    with pytest.raises(NotFound):
        transition_listing(
            actor=intruder, listing_id=listing_id, expected_version=1, action="submit"
        )
    bad = payload(category)
    bad["currency"] = "usd"
    assert api.post("/api/v1/listings/", bad, format="json").status_code == 400
    assert Listing.objects.count() == 1


def test_transition_policy_and_field_validation():
    assert next_status("draft", "submit") == "pending"
    assert next_status("published", "archive") == "archived"
    for from_state, action in [("draft", "approve"), ("pending", "submit"), ("sold", "submit")]:
        with pytest.raises(ListingRuleError):
            next_status(from_state, action)
    for invalid in [
        {"title": "a"},
        {"title": "Valid", "price_minor": True},
        {"title": "Valid", "price_minor": 1, "currency": "usd"},
        {"title": "Valid", "price_minor": 1, "currency": "USD", "attributes": {"bad": {}}},
    ]:
        with pytest.raises(ListingRuleError):
            normalize_fields(invalid)


def test_public_filters_and_inactive_categories():
    category = ListingCategory.objects.create(slug="cars", title="Cars")
    user, api = user_client("filter-ads@example.test")
    _, moderator = user_client("filter-moderator@example.test", superuser=True)
    listing_id = api.post("/api/v1/listings/", payload(category), format="json").data["id"]
    api.post(f"/api/v1/listings/{listing_id}/submit/", {"expected_version": 0}, format="json")
    moderator.post(
        f"/api/v1/listings/{listing_id}/moderate/",
        {"expected_version": 1, "decision": "approve"},
        format="json",
    )
    public = APIClient()
    assert (
        public.get("/api/v1/listings/?category=cars&min_price=119000&q=laptop").data["count"] == 1
    )
    assert public.get("/api/v1/listings/?category=houses").data["count"] == 0
    assert public.get("/api/v1/listings/?max_price=1000").data["count"] == 0
    assert public.get("/api/v1/listings/?min_price=garbage").status_code == 400
    category.active = False
    category.save(update_fields=("active",))
    assert api.post("/api/v1/listings/", payload(category), format="json").status_code == 400
    assert user.is_active


@pytest.mark.django_db(transaction=True)
def test_postgresql_race_only_submits_listing_once():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    category = ListingCategory.objects.create(slug="bikes", title="Bikes")
    seller, api = user_client("race-seller@example.test")
    listing_id = api.post("/api/v1/listings/", payload(category), format="json").data["id"]
    barrier = Barrier(2)

    def worker(_index):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            try:
                transition_listing(
                    actor=seller, listing_id=listing_id, expected_version=0, action="submit"
                )
            except StaleListing:
                return "stale"
            return "submitted"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(worker, range(2)))
    assert sorted(outcomes) == ["stale", "submitted"]
    listing = Listing.objects.get(pk=listing_id)
    assert listing.version == 1
    assert listing.status == "pending"
