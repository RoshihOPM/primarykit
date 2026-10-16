"""Standalone private Storage must never require Organizations."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.storage.models import StoredFile
from apps.users.models import User

pytestmark = pytest.mark.django_db
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


@pytest.fixture
def disk(tmp_path, settings):
    settings.STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path), "base_url": None},
        },
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    settings.STORAGE_MAX_FILE_BYTES = 10 * 1024 * 1024
    settings.STORAGE_ALLOWED_MIME_TYPES = ("image/png",)
    return tmp_path


def identity(email, *, superuser=False):
    user = User.objects.create_user(
        email=email,
        password="strong-private-test-password",
        email_verified=True,
        is_superuser=superuser,
        is_staff=superuser,
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return user, api


def upload_png(api):
    return api.post(
        reverse("stored-files-list"),
        {"file": SimpleUploadedFile("private.png", PNG, content_type="image/png")},
        format="multipart",
    )


def test_personal_upload_is_private_and_downloadable(disk):
    owner, client = identity("personal-owner@example.test")
    result = upload_png(client)
    assert result.status_code == 201, result.data
    file = StoredFile.objects.get(pk=result.data["id"])
    assert file.owner_id == owner.pk
    assert file.organization_id is None
    assert file.object_key.startswith(f"private/users/{owner.pk}/")
    assert (disk / file.object_key).read_bytes() == PNG
    download = client.get(reverse("stored-files-download", kwargs={"pk": file.pk}))
    assert download.status_code == 200
    assert b"".join(download.streaming_content) == PNG
    assert download["Cache-Control"] == "private, no-store"
    assert "object_key" not in result.data


def test_personal_files_are_invisible_to_others_and_global_admin(disk):
    _, owner_client = identity("private-first@example.test")
    _, other_client = identity("private-second@example.test")
    _, root_client = identity("private-root@example.test", superuser=True)
    created = upload_png(owner_client)
    assert created.status_code == 201
    url = reverse("stored-files-detail", kwargs={"pk": created.data["id"]})
    download = reverse("stored-files-download", kwargs={"pk": created.data["id"]})
    assert other_client.get(reverse("stored-files-list")).data["count"] == 0
    assert root_client.get(reverse("stored-files-list")).data["count"] == 0
    for client in (other_client, root_client):
        assert client.get(url).status_code == 404
        assert client.get(download).status_code == 404
        assert client.delete(url).status_code == 404
    assert owner_client.delete(url).status_code == 204
    assert owner_client.get(download).status_code == 404


def test_personal_storage_rejects_invalid_upload_and_anonymous(disk):
    _, client = identity("private-validation@example.test")
    assert APIClient().get(reverse("stored-files-list")).status_code == 401
    bad = client.post(
        reverse("stored-files-list"),
        {"file": SimpleUploadedFile("exploit.html", b"<script>alert(1)</script>")},
        format="multipart",
    )
    assert bad.status_code == 400
    assert not StoredFile.objects.exists()
