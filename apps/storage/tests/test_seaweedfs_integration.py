"""Real SeaweedFS integration; only runs when explicitly enabled and S3 is running."""

import os
import time

import pytest
from django.conf import settings
from django.core.files.storage import storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.storage.models import StoredFile
from apps.users.models import User

pytestmark = pytest.mark.django_db

PNG = bytes.fromhex("89504e470d0a1a0a") + bytes(24)


@pytest.mark.skipif(
    os.environ.get("PRIMARYKIT_SEAWEEDFS_INTEGRATION") != "1",
    reason="Requires live SeaweedFS S3 credentials and service",
)
def test_private_s3_upload_download_and_idor():
    assert settings.STORAGE_BACKEND == "s3"
    assert settings.STORAGES["default"]["BACKEND"] == "storages.backends.s3.S3Storage"
    storage = storages["default"]
    # Wait for the S3 gateway and the bucket initialized by weed mini.
    deadline = time.monotonic() + 60
    while True:
        try:
            storage.connection.meta.client.head_bucket(
                Bucket=settings.STORAGES["default"]["OPTIONS"]["bucket_name"]
            )
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)

    owner = User.objects.create_user(
        email="seaweed-owner@example.test",
        password="Long-test-password-123456",
        email_verified=True,
    )
    stranger = User.objects.create_user(
        email="seaweed-other@example.test",
        password="Long-test-password-123457",
        email_verified=True,
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(owner).access_token}")
    other = APIClient()
    other.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(stranger).access_token}")

    result = api.post(
        reverse("stored-files-list"),
        {"file": SimpleUploadedFile("photo.png", PNG, content_type="image/png")},
        format="multipart",
    )
    assert result.status_code == 201, getattr(result, "data", result.content)
    item = StoredFile.objects.get(pk=result.data["id"])
    try:
        assert storage.exists(item.object_key)
        with storage.open(item.object_key, "rb") as reader:
            assert reader.read() == PNG
        assert (
            other.get(reverse("stored-files-download", kwargs={"pk": item.pk})).status_code == 404
        )
        response = api.get(reverse("stored-files-download", kwargs={"pk": item.pk}))
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == PNG
        assert api.delete(reverse("stored-files-detail", kwargs={"pk": item.pk})).status_code == 204
        assert api.get(reverse("stored-files-download", kwargs={"pk": item.pk})).status_code == 404
    finally:
        storage.delete(item.object_key)
