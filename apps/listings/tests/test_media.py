"""Media security, moderation, retention and genuine PostgreSQL lock races."""
import io
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import close_old_connections, connection, connections
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.listings.media import MAX_IMAGES, add_image, private_storage
from apps.listings.models import Listing, ListingCategory, ListingImage
from apps.listings.services import StaleListing
from apps.users.models import User

Image = pytest.importorskip("PIL.Image")

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def isolated_private_storage(settings, tmp_path):
    private = tmp_path / "sensitive-listing-media"
    config = {
        **settings.STORAGES,
        "listings_private": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(private), "base_url": None},
        },
    }
    with override_settings(LISTINGS_MEDIA_ENABLED=True, STORAGES=config):
        yield private


def api_user(email, *, moderator=False):
    user = User.objects.create_user(
        email=email,
        password="secure-listing-media-password",
        email_verified=True,
        is_staff=moderator,
        is_superuser=moderator,
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return user, api


def photo_bytes(*, fmt="PNG", dimensions=(32, 24), marker=None):
    output = io.BytesIO()
    image = Image.new("RGB", dimensions, (120, 50, 210))
    if marker is not None:
        exif = Image.Exif()
        exif[270] = marker
        image.save(output, format=fmt, exif=exif)
    else:
        image.save(output, format=fmt)
    return output.getvalue()


def uploaded(data=None, *, content_type="image/png"):
    return SimpleUploadedFile("photo.png", data or photo_bytes(), content_type=content_type)


def create_listing(api):
    category = ListingCategory.objects.create(slug="cars", title="Cars")
    response = api.post(
        "/api/v1/listings/",
        {"category": str(category.pk), "title": "A decent car",
         "price_minor": 500000, "currency": "KZT"},
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data["id"]


def photo_url(listing_id, image_id=None):
    root = f"/api/v1/listings/{listing_id}/media/"
    return root if image_id is None else f"{root}{image_id}/"


def upload(api, listing_id, version, blob=None):
    return api.post(
        photo_url(listing_id),
        {"expected_version": version, "file": blob or uploaded()},
        format="multipart",
    )


def submit(api, listing_id, version):
    return api.post(
        f"/api/v1/listings/{listing_id}/submit/",
        {"expected_version": version}, format="json",
    )


def moderate_photo(api, listing_id, image_id, version, decision="approve"):
    return api.post(
        f"{photo_url(listing_id, image_id)}moderate/",
        {"expected_version": version, "decision": decision},
        format="json",
    )


def approve_listing(api, listing_id, version):
    return api.post(
        f"/api/v1/listings/{listing_id}/moderate/",
        {"expected_version": version, "decision": "approve"}, format="json",
    )


def test_moderated_photo_public_visibility_and_immediate_revocation():
    seller, seller_api = api_user("photo-seller@example.test")
    _, moderator = api_user("photo-reviewer@example.test", moderator=True)
    _, stranger = api_user("photo-stranger@example.test")
    public = APIClient()
    listing = create_listing(seller_api)
    created = upload(seller_api, listing, 0)
    assert created.status_code == 201, created.data
    image_id = created.data["id"]
    assert created.data["status"] == "pending"
    assert created.data["url"] == photo_url(listing, image_id)
    assert "private_key" not in created.data
    assert public.get(photo_url(listing)).status_code == 404
    assert public.get(photo_url(listing, image_id)).status_code == 404
    assert stranger.get(photo_url(listing, image_id)).status_code == 404
    assert seller_api.get(photo_url(listing, image_id)).status_code == 200

    assert submit(seller_api, listing, 1).status_code == 200
    assert approve_listing(moderator, listing, 2).status_code == 400
    assert moderate_photo(seller_api, listing, image_id, 2).status_code == 403
    reviewed = moderate_photo(moderator, listing, image_id, 2)
    assert reviewed.status_code == 200, reviewed.data
    assert reviewed.data["status"] == "approved"
    assert approve_listing(moderator, listing, 3).status_code == 200
    shown = public.get(photo_url(listing))
    assert shown.status_code == 200
    assert len(shown.data) == 1
    response = public.get(photo_url(listing, image_id))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
    assert response["Cache-Control"] == "no-store, max-age=0"
    assert response["X-Content-Type-Options"] == "nosniff"
    with Image.open(io.BytesIO(b"".join(response.streaming_content))) as image:
        assert image.format == "JPEG"

    archived = seller_api.post(
        f"/api/v1/listings/{listing}/archive/",
        {"expected_version": 4}, format="json",
    )
    assert archived.status_code == 200
    assert public.get(photo_url(listing, image_id)).status_code == 404
    assert public.get(photo_url(listing)).status_code == 404
    # Revocation is status based, not a best-effort CDN purge.
    assert seller_api.get(photo_url(listing, image_id)).status_code == 200
    assert seller.pk == Listing.objects.get(pk=listing).owner_id


def test_owner_idor_and_superuser_cannot_change_sellers_photos():
    seller, seller_api = api_user("id-seller@example.test")
    outsider, outsider_api = api_user("id-outsider@example.test")
    _, admin = api_user("id-admin@example.test", moderator=True)
    listing = create_listing(seller_api)
    assert upload(outsider_api, listing, 0).status_code == 404
    assert upload(admin, listing, 0).status_code == 404
    created = upload(seller_api, listing, 0)
    image_id = created.data["id"]
    assert outsider_api.get(photo_url(listing, image_id)).status_code == 404
    assert admin.get(photo_url(listing, image_id)).status_code == 404
    assert outsider_api.delete(
        photo_url(listing, image_id),
        {"expected_version": 1}, format="json",
    ).status_code == 404
    assert admin.delete(
        photo_url(listing, image_id),
        {"expected_version": 1}, format="json",
    ).status_code == 404
    assert APIClient().post(photo_url(listing), {}).status_code in (401, 403, 404)
    assert outsider.pk != seller.pk
    assert ListingImage.objects.count() == 1


def test_exif_removed_orientation_normalized_and_type_spoof_rejected():
    seller, api = api_user("sanitize-photo@example.test")
    listing = create_listing(api)
    source = photo_bytes(fmt="JPEG", marker="PRIVATE GPS / device information")
    rejected = upload(api, listing, 0, uploaded(source, content_type="image/png"))
    assert rejected.status_code == 400
    assert ListingImage.objects.count() == 0
    accepted = upload(api, listing, 0, uploaded(source, content_type="image/jpeg"))
    assert accepted.status_code == 201, accepted.data
    image = ListingImage.objects.get(pk=accepted.data["id"])
    private = private_storage()
    with private.open(image.private_key, "rb") as handle:
        content = handle.read()
    assert b"PRIVATE GPS" not in content
    with Image.open(io.BytesIO(content)) as sanitized:
        assert sanitized.getexif() == {}
        assert sanitized.size == (32, 24)
    assert image.private_key.startswith("listing-photos/")
    assert image.private_key not in str(accepted.data)
    assert seller.pk == Listing.objects.get(pk=listing).owner_id


def test_reject_bad_files_limits_and_oversized_pixels(monkeypatch):
    _, api = api_user("limits-photo@example.test")
    listing = create_listing(api)
    invalid = upload(api, listing, 0, uploaded(b"not a real PNG"))
    assert invalid.status_code == 400
    invalid = upload(api, listing, 0, uploaded(photo_bytes(), content_type="image/gif"))
    assert invalid.status_code == 400
    from apps.listings import media

    monkeypatch.setattr(media, "MAX_UPLOAD_BYTES", 10)
    assert upload(api, listing, 0).status_code == 400
    monkeypatch.setattr(media, "MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
    monkeypatch.setattr(media, "MAX_IMAGE_PIXELS", 10)
    assert upload(api, listing, 0).status_code == 400
    monkeypatch.setattr(media, "MAX_IMAGE_PIXELS", 16_000_000)
    for version in range(MAX_IMAGES):
        response = upload(api, listing, version)
        assert response.status_code == 201, response.data
    assert upload(api, listing, MAX_IMAGES).status_code == 400
    assert ListingImage.objects.count() == MAX_IMAGES


def test_photo_moderator_negative_paths_rejections_and_stale_writes():
    seller, api = api_user("moderation-photo@example.test")
    _, moderator = api_user("moderation-admin@example.test", moderator=True)
    _, other = api_user("moderation-other@example.test")
    listing = create_listing(api)
    photo = upload(api, listing, 0).data["id"]
    assert moderate_photo(moderator, listing, photo, 1).status_code == 400
    assert submit(api, listing, 1).status_code == 200
    assert moderate_photo(other, listing, photo, 2).status_code == 403
    assert moderate_photo(moderator, listing, photo, 1).status_code == 409
    reject = moderate_photo(moderator, listing, photo, 2, decision="reject")
    assert reject.status_code == 200
    assert reject.data["status"] == "rejected"
    assert moderate_photo(moderator, listing, photo, 3).status_code == 400
    assert approve_listing(moderator, listing, 3).status_code == 200
    assert APIClient().get(photo_url(listing)).data == []
    assert APIClient().get(photo_url(listing, photo)).status_code == 404
    assert api.get(photo_url(listing, photo)).status_code == 200
    assert seller.pk == Listing.objects.get(pk=listing).owner_id


def test_delete_photo_versioning_and_disable_flag(settings):
    _, api = api_user("delete-photo@example.test")
    listing = create_listing(api)
    image = upload(api, listing, 0).data["id"]
    assert api.delete(
        photo_url(listing, image),
        {"expected_version": 0}, format="json",
    ).status_code == 409
    assert api.delete(
        photo_url(listing, image),
        {"expected_version": 1}, format="json",
    ).status_code == 204
    assert ListingImage.objects.count() == 0
    assert api.get(photo_url(listing, image)).status_code == 404
    settings.LISTINGS_MEDIA_ENABLED = False
    assert api.get(photo_url(listing)).status_code == 404
    assert upload(api, listing, 2).status_code == 404


def test_orphan_reclamation_and_closed_listing_retention():
    _, api = api_user("orphan-photo@example.test")
    listing = create_listing(api)
    photo = upload(api, listing, 0).data["id"]
    key = ListingImage.objects.get(pk=photo).private_key
    assert api.post(
        f"/api/v1/listings/{listing}/archive/",
        {"expected_version": 1}, format="json",
    ).status_code == 200
    Listing.objects.filter(pk=listing).update(updated_at=timezone.now() - timedelta(days=10))
    orphan_name = "listing-photos/" + "e" * 32 + ".jpg"
    storage = private_storage()
    storage.save(orphan_name, ContentFile(photo_bytes()))
    path = storage.path(orphan_name)
    then = (timezone.now() - timedelta(days=10)).timestamp()
    os.utime(path, (then, then))
    call_command("purge_listing_media", days=7)
    assert ListingImage.objects.filter(pk=photo).count() == 0
    assert storage.exists(orphan_name) is False
    # Physical deletion after commit is separate; old keys are orphan-sweepable.
    assert key != orphan_name


@pytest.mark.django_db(transaction=True)
def test_postgres_two_writers_one_gallery_slot():
    if connection.vendor != "postgresql":
        pytest.skip("Concurrent row locks require PostgreSQL")
    seller, api = api_user("pg-photo@example.test")
    listing = create_listing(api)
    barrier = Barrier(2)

    def upload_racing(_):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            try:
                add_image(
                    actor=seller, listing_id=listing, expected_version=0,
                    uploaded=uploaded(),
                )
            except StaleListing:
                return "stale"
            return "ok"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(upload_racing, [1, 2]))
    assert sorted(result) == ["ok", "stale"]
    assert ListingImage.objects.filter(listing_id=listing).count() == 1
    assert Listing.objects.get(pk=listing).version == 1
