import hashlib
from unittest.mock import patch

import pytest
from django.apps import apps as django_apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.storage.models import StoredFile
from apps.users.models import User

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


@pytest.fixture
def private_disk(tmp_path, settings):
    settings.STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path), "base_url": None},
        },
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    settings.STORAGE_MAX_FILE_BYTES = 10 * 1024 * 1024
    settings.STORAGE_ALLOWED_MIME_TYPES = [
        "image/png",
        "image/jpeg",
        "image/webp",
        "application/pdf",
    ]
    return tmp_path


def user(email, *, admin=False):
    return User.objects.create_user(
        email=email,
        password="long-test-password-456",
        email_verified=True,
        is_superuser=admin,
        is_staff=admin,
    )


def client_for(member):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member).access_token}")
    return client


def png_upload(filename="profile.png", body=PNG):
    return SimpleUploadedFile(filename, body, content_type="image/png")


def test_upload_and_authorized_private_download(private_disk):
    member = user("file-owner@example.com")
    api = client_for(member)
    response = api.post(reverse("stored-files-list"), {"file": png_upload()}, format="multipart")
    assert response.status_code == 201, response.data
    info = response.data
    assert "object_key" not in info and "owner" not in info
    assert info["sha256"] == hashlib.sha256(PNG).hexdigest()
    file = StoredFile.objects.get(pk=info["id"])
    assert file.owner == member
    assert file.object_key.startswith("private/")
    assert (private_disk / file.object_key).read_bytes() == PNG

    download = api.get(reverse("stored-files-download", kwargs={"pk": file.pk}))
    assert download.status_code == 200
    assert b"".join(download.streaming_content) == PNG
    assert download["Cache-Control"] == "private, no-store"
    assert download["X-Content-Type-Options"] == "nosniff"
    assert "attachment" in download["Content-Disposition"]
    if django_apps.is_installed("apps.audit"):
        from apps.audit.models import AuditEvent

        assert AuditEvent.objects.filter(
            action="storage.file.uploaded", target_id=str(file.pk)
        ).exists()


def test_idor_and_list_scoping(private_disk):
    owner = user("owner@example.com")
    stranger = user("other@example.com")
    staff = user("admin@example.com", admin=True)
    owner_client = client_for(owner)
    created = owner_client.post(
        reverse("stored-files-list"), {"file": png_upload()}, format="multipart"
    )
    pk = created.data["id"]
    other_client = client_for(stranger)
    assert other_client.get(reverse("stored-files-list")).data["count"] == 0
    assert other_client.get(reverse("stored-files-detail", kwargs={"pk": pk})).status_code == 404
    assert other_client.get(reverse("stored-files-download", kwargs={"pk": pk})).status_code == 404
    assert other_client.delete(reverse("stored-files-detail", kwargs={"pk": pk})).status_code == 404
    assert (
        client_for(staff).get(reverse("stored-files-detail", kwargs={"pk": pk})).status_code == 200
    )


@pytest.mark.parametrize(
    "filename,content",
    [
        ("payload.html", PNG),
        ("fake.png", b"<script>bad()</script>"),
        ("empty.png", b""),
        ("evil.svg", b"<svg><script>x</script></svg>"),
    ],
)
def test_disallowed_files_rejected(private_disk, filename, content):
    member = user(f"member-{filename.replace('.', '_')}@example.com")
    response = client_for(member).post(
        reverse("stored-files-list"),
        {"file": png_upload(filename, content)},
        format="multipart",
    )
    assert response.status_code == 400
    assert StoredFile.objects.count() == 0
    assert list(private_disk.rglob("*")) == []


def test_reject_large_upload(private_disk, settings):
    settings.STORAGE_MAX_FILE_BYTES = 16
    owner = user("large@example.com")
    response = client_for(owner).post(
        reverse("stored-files-list"),
        {"file": png_upload()},
        format="multipart",
    )
    assert response.status_code == 400
    assert not StoredFile.objects.exists()


def test_soft_delete_hides_file_and_leaves_blob_for_retention(private_disk):
    member = user("del@example.com")
    api = client_for(member)
    created = api.post(reverse("stored-files-list"), {"file": png_upload()}, format="multipart")
    file = StoredFile.objects.get(pk=created.data["id"])
    path = private_disk / file.object_key
    assert path.exists()
    assert api.delete(reverse("stored-files-detail", kwargs={"pk": file.pk})).status_code == 204
    file.refresh_from_db()
    assert file.deleted_at is not None
    assert path.exists()
    assert api.get(reverse("stored-files-download", kwargs={"pk": file.pk})).status_code == 404
    assert api.delete(reverse("stored-files-detail", kwargs={"pk": file.pk})).status_code == 404
    if django_apps.is_installed("apps.audit"):
        from apps.audit.models import AuditEvent

        assert AuditEvent.objects.filter(action="storage.file.deleted", target_id=str(file.pk)).exists()


def test_failed_metadata_write_cleans_up_blob(private_disk):
    member = user("rollback@example.com")
    with patch(
        "apps.storage.services.record_audit_event", side_effect=RuntimeError("audit offline")
    ):
        with pytest.raises(RuntimeError):
            client_for(member).post(
                reverse("stored-files-list"),
                {"file": png_upload()},
                format="multipart",
            )
    assert StoredFile.objects.count() == 0
    assert list(private_disk.rglob("*.png")) == []
    assert not any(p.is_file() for p in private_disk.rglob("*"))
