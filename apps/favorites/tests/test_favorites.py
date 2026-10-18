"""Bookmark visibility, saved-filter boundaries, quota and PostgreSQL race tests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections, connection, connections
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.favorites.domain import MAX_SAVED_SEARCHES, normalize_filters
from apps.favorites.models import Favorite, SavedSearch
from apps.favorites.services import create_search
from apps.listings.models import Listing, ListingCategory
from apps.users.models import User

pytestmark = pytest.mark.django_db


def user_client(email, *, superuser=False):
    user = User.objects.create_user(
        email=email,
        password="long-favorites-test-password",
        email_verified=True,
        is_staff=superuser,
        is_superuser=superuser,
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return user, api


def make_listing(*, owner, status=Listing.Status.PUBLISHED, category=None):
    category = category or ListingCategory.objects.create(
        slug=f"category-{uuid4().hex[:10]}", title="Computers"
    )
    return Listing.objects.create(
        owner=owner,
        category=category,
        title="Laptop",
        price_minor=120000,
        currency="KZT",
        status=status,
    )


def test_favorites_are_private_idempotent_and_only_public_listings():
    seller, _ = user_client("seller-favs@example.test")
    alice, a = user_client("alice-favs@example.test")
    bob, b = user_client("bob-favs@example.test")
    _, admin = user_client("admin-favs@example.test", superuser=True)
    public = APIClient()
    published = make_listing(owner=seller)
    draft = make_listing(owner=seller, status=Listing.Status.DRAFT)
    endpoint = "/api/v1/favorites/"
    assert public.get(endpoint).status_code in (401, 403)
    assert public.post(endpoint, {"listing_id": str(published.pk)}).status_code in (401, 403)
    assert a.post(endpoint, {"listing_id": str(draft.pk)}).status_code == 404
    assert a.post(endpoint, {"listing_id": str(uuid4())}).status_code == 404
    created = a.post(endpoint, {"listing_id": str(published.pk)}, format="json")
    assert created.status_code == 201, created.data
    duplicate = a.post(endpoint, {"listing_id": str(published.pk)}, format="json")
    assert duplicate.status_code == 200
    assert duplicate.data["id"] == created.data["id"]
    assert Favorite.objects.count() == 1
    assert a.get(endpoint).data["count"] == 1
    favorite_id = created.data["id"]
    detail = f"{endpoint}{favorite_id}/"
    assert b.get(endpoint).data["count"] == 0
    assert admin.get(endpoint).data["count"] == 0
    assert b.get(detail).status_code == 404
    assert admin.get(detail).status_code == 404
    assert b.delete(detail).status_code == 404
    assert admin.delete(detail).status_code == 404
    assert a.delete(detail).status_code == 204
    assert Favorite.objects.count() == 0


def test_favorite_hides_unpublished_and_disabled_seller_and_can_be_removed():
    seller, _ = user_client("seller-hidden-favs@example.test")
    _, api = user_client("reader-hidden-favs@example.test")
    listing = make_listing(owner=seller)
    favorite_id = api.post("/api/v1/favorites/", {"listing_id": str(listing.pk)}).data["id"]
    listing.status = Listing.Status.ARCHIVED
    listing.save(update_fields=("status",))
    assert api.get("/api/v1/favorites/").data["count"] == 0
    assert api.get(f"/api/v1/favorites/{favorite_id}/").status_code == 404
    assert api.delete(f"/api/v1/favorites/{favorite_id}/").status_code == 204
    listing.status = Listing.Status.PUBLISHED
    listing.save(update_fields=("status",))
    saved = api.post("/api/v1/favorites/", {"listing_id": str(listing.pk)})
    assert saved.status_code == 201
    seller.is_active = False
    seller.save(update_fields=("is_active",))
    assert api.get("/api/v1/favorites/").data["count"] == 0
    assert api.post("/api/v1/favorites/", {"listing_id": str(listing.pk)}).status_code == 404


def test_favorites_list_paginates_and_rejects_sender_mass_assignment():
    seller, _ = user_client("seller-page-favs@example.test")
    reader, api = user_client("reader-page-favs@example.test")
    for _ in range(4):
        listing = make_listing(owner=seller)
        assert (
            api.post(
                "/api/v1/favorites/", {"listing_id": str(listing.pk), "owner": str(reader.pk)}
            ).status_code
            == 400
        )
        assert api.post("/api/v1/favorites/", {"listing_id": str(listing.pk)}).status_code == 201
    result = api.get("/api/v1/favorites/?page_size=2")
    assert result.status_code == 200
    assert result.data["count"] == 4
    assert len(result.data["results"]) == 2


def test_filter_domain_denies_unknown_nested_oversized_and_bad_prices():
    assert normalize_filters({"q": "  laptop ", "min_price": 100}) == {
        "q": "laptop",
        "min_price": 100,
    }
    for candidate in [
        {},
        [],
        {"unknown": "x"},
        {"q": " "},
        {"q": "z" * 81},
        {"category": "../bad"},
        {"location": {"$regex": "x"}},
        {"min_price": True},
        {"min_price": -1},
        {"max_price": 10**16},
        {"min_price": 200, "max_price": 100},
    ]:
        with pytest.raises(ValueError):
            normalize_filters(candidate)


def test_saved_search_is_private_bounded_and_patch_is_allowlisted():
    alice, api = user_client("alice-search@example.test")
    _, outsider = user_client("outsider-search@example.test")
    _, admin = user_client("admin-search@example.test", superuser=True)
    uri = "/api/v1/saved-searches/"
    payload = {"name": "My laptops", "filters": {"q": " laptop ", "min_price": 100}}
    assert APIClient().get(uri).status_code in (401, 403)
    response = api.post(uri, payload, format="json")
    assert response.status_code == 201, response.data
    key = response.data["id"]
    assert response.data["filters"] == {"q": "laptop", "min_price": 100}
    assert response.data["name"] == "My laptops"
    url = f"{uri}{key}/"
    assert api.get(uri).data["count"] == 1
    assert outsider.get(uri).data["count"] == 0
    assert admin.get(uri).data["count"] == 0
    for other in (outsider, admin):
        assert other.get(url).status_code == 404
        assert other.patch(url, {"name": "Hacked"}).status_code == 404
        assert other.delete(url).status_code == 404
    assert api.post(uri, {"name": "bad", "filters": {"owner": str(alice.pk)}}).status_code == 400
    assert (
        api.post(uri, {"name": "bad", "filters": {"q": "ok"}, "owner": str(alice.pk)}).status_code
        == 400
    )
    assert api.patch(url, {"filters": {"q": " "}}, format="json").status_code == 400
    assert api.patch(url, {"owner": str(alice.pk)}).status_code == 400
    updated = api.patch(url, {"filters": {"category": "cars", "max_price": 999}}, format="json")
    assert updated.status_code == 200
    assert updated.data["filters"] == {"category": "cars", "max_price": 999}
    assert api.delete(url).status_code == 204
    assert not SavedSearch.objects.filter(pk=key).exists()


def test_saved_search_count_limit_and_reuse_deleted_slots():
    owner, api = user_client("limit-favs@example.test")
    uri = "/api/v1/saved-searches/"
    for i in range(MAX_SAVED_SEARCHES):
        assert (
            api.post(
                uri, {"name": f"Search {i}", "filters": {"q": "laptop"}}, format="json"
            ).status_code
            == 201
        )
    assert api.get(uri).data["count"] == MAX_SAVED_SEARCHES
    assert api.post(uri, {"name": "Too many", "filters": {"q": "laptop"}}).status_code == 400
    first = SavedSearch.objects.filter(owner=owner).first()
    assert api.delete(f"{uri}{first.pk}/").status_code == 204
    assert api.post(uri, {"name": "Reused", "filters": {"q": "laptop"}}).status_code == 201


@pytest.mark.django_db(transaction=True)
def test_postgres_two_writers_cannot_exceed_saved_search_cap():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locking.")
    owner, _ = user_client("pg-limit-favs@example.test")
    for i in range(MAX_SAVED_SEARCHES - 1):
        SavedSearch.objects.create(owner=owner, name=f"seed-{i}", filters={"q": "seed"})
    barrier = Barrier(2)

    def write(index):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            try:
                return (
                    create_search(actor=owner, name=f"parallel-{index}", filters={"q": "laptop"}).pk
                    is not None
                )
            except Exception as exc:
                from rest_framework.exceptions import ValidationError

                if isinstance(exc, ValidationError):
                    return False
                raise
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, (1, 2)))
    assert sorted(results) == [False, True]
    assert SavedSearch.objects.filter(owner=owner).count() == MAX_SAVED_SEARCHES
