import hashlib
import uuid
from unittest.mock import patch

import pytest
from django.apps import apps as django_apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.exceptions import NotFound
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.organizations.models import Membership, Organization
from apps.storage.models import StoredFile
from apps.storage.policies import resolve_file_scope
from apps.storage.services import save_private_file, soft_delete_private_file
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


def org_for(owner):
    organization = Organization.objects.create(name="Test organization", slug=uuid.uuid4().hex)
    Membership.objects.create(organization=organization, user=owner, role=Membership.Role.OWNER)
    return organization


def client_for(member):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member).access_token}")
    return client


def png_upload(filename="profile.png", body=PNG):
    return SimpleUploadedFile(filename, body, content_type="image/png")


def test_upload_and_authorized_private_download(private_disk):
    member = user("file-owner@example.com")
    org = org_for(member)
    api = client_for(member)
    response = api.post(
        reverse("stored-files-list", kwargs={"org_id": org.pk}),
        {"file": png_upload()},
        format="multipart",
    )
    assert response.status_code == 201, response.data
    info = response.data
    assert "object_key" not in info and "owner" not in info
    assert info["sha256"] == hashlib.sha256(PNG).hexdigest()
    file = StoredFile.objects.get(pk=info["id"])
    assert file.owner == member
    assert file.organization_id == org.pk
    assert file.object_key.startswith(f"private/organizations/{org.pk}/")
    assert (private_disk / file.object_key).read_bytes() == PNG

    download = api.get(reverse("stored-files-download", kwargs={"org_id": org.pk, "pk": file.pk}))
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
    org = org_for(owner)
    stranger = user("other@example.com")
    staff = user("admin@example.com", admin=True)
    Membership.objects.create(organization=org, user=staff, role=Membership.Role.ADMIN)
    Membership.objects.create(organization=org, user=stranger, role=Membership.Role.MEMBER)
    owner_client = client_for(owner)
    created = owner_client.post(
        reverse("stored-files-list", kwargs={"org_id": org.pk}),
        {"file": png_upload()},
        format="multipart",
    )
    pk = created.data["id"]
    other_client = client_for(stranger)
    assert (
        other_client.get(reverse("stored-files-list", kwargs={"org_id": org.pk})).data["count"] == 0
    )
    assert (
        other_client.get(
            reverse("stored-files-detail", kwargs={"org_id": org.pk, "pk": pk})
        ).status_code
        == 404
    )
    assert (
        other_client.get(
            reverse("stored-files-download", kwargs={"org_id": org.pk, "pk": pk})
        ).status_code
        == 404
    )
    assert (
        other_client.delete(
            reverse("stored-files-detail", kwargs={"org_id": org.pk, "pk": pk})
        ).status_code
        == 404
    )
    assert (
        client_for(staff)
        .get(reverse("stored-files-detail", kwargs={"org_id": org.pk, "pk": pk}))
        .status_code
        == 200
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
    org = org_for(member)
    response = client_for(member).post(
        reverse("stored-files-list", kwargs={"org_id": org.pk}),
        {"file": png_upload(filename, content)},
        format="multipart",
    )
    assert response.status_code == 400
    assert StoredFile.objects.count() == 0
    assert list(private_disk.rglob("*")) == []


def test_reject_large_upload(private_disk, settings):
    settings.STORAGE_MAX_FILE_BYTES = 16
    owner = user("large@example.com")
    org = org_for(owner)
    response = client_for(owner).post(
        reverse("stored-files-list", kwargs={"org_id": org.pk}),
        {"file": png_upload()},
        format="multipart",
    )
    assert response.status_code == 400
    assert not StoredFile.objects.exists()


def test_soft_delete_hides_file_and_leaves_blob_for_retention(private_disk):
    member = user("del@example.com")
    org = org_for(member)
    api = client_for(member)
    created = api.post(
        reverse("stored-files-list", kwargs={"org_id": org.pk}),
        {"file": png_upload()},
        format="multipart",
    )
    file = StoredFile.objects.get(pk=created.data["id"])
    path = private_disk / file.object_key
    assert path.exists()
    assert (
        api.delete(
            reverse("stored-files-detail", kwargs={"org_id": org.pk, "pk": file.pk})
        ).status_code
        == 204
    )
    file.refresh_from_db()
    assert file.deleted_at is not None
    assert path.exists()
    assert (
        api.get(
            reverse("stored-files-download", kwargs={"org_id": org.pk, "pk": file.pk})
        ).status_code
        == 404
    )
    assert (
        api.delete(
            reverse("stored-files-detail", kwargs={"org_id": org.pk, "pk": file.pk})
        ).status_code
        == 404
    )
    if django_apps.is_installed("apps.audit"):
        from apps.audit.models import AuditEvent

        assert AuditEvent.objects.filter(
            action="storage.file.deleted", target_id=str(file.pk)
        ).exists()


def test_failed_metadata_write_cleans_up_blob(private_disk):
    member = user("rollback@example.com")
    org = org_for(member)
    with patch(
        "apps.storage.services.record_audit_event", side_effect=RuntimeError("audit offline")
    ):
        with pytest.raises(RuntimeError):
            client_for(member).post(
                reverse("stored-files-list", kwargs={"org_id": org.pk}),
                {"file": png_upload()},
                format="multipart",
            )
    assert StoredFile.objects.count() == 0
    assert list(private_disk.rglob("*.png")) == []
    assert not any(p.is_file() for p in private_disk.rglob("*"))


def test_cross_tenant_file_idor_and_no_global_superuser_bypass(private_disk):
    owner = user("tenant-owner@example.com")
    org = org_for(owner)
    another = user("tenant-other@example.com")
    other_org = org_for(another)
    superuser = user("tenant-root@example.com", admin=True)
    Membership.objects.create(organization=other_org, user=superuser, role=Membership.Role.ADMIN)
    api = client_for(owner)
    response = api.post(
        reverse("stored-files-list", kwargs={"org_id": org.pk}),
        {"file": png_upload()},
        format="multipart",
    )
    assert response.status_code == 201
    pk = response.data["id"]
    detail = reverse("stored-files-detail", kwargs={"org_id": org.pk, "pk": pk})
    wrong_detail = reverse("stored-files-detail", kwargs={"org_id": other_org.pk, "pk": pk})
    assert client_for(superuser).get(detail).status_code == 404
    assert client_for(another).get(wrong_detail).status_code == 404
    assert client_for(another).delete(wrong_detail).status_code == 404
    assert api.get("/api/v1/files/").data["count"] == 0

    Membership.objects.create(organization=other_org, user=owner, role=Membership.Role.ADMIN)
    assert api.get(wrong_detail).status_code == 404


def test_tenant_admin_member_revocation_and_service_layer_security(private_disk):
    owner = user("access-owner@example.com")
    org = org_for(owner)
    member = user("access-member@example.com")
    admin = user("access-admin@example.com")
    grant = Membership.objects.create(organization=org, user=member, role=Membership.Role.MEMBER)
    Membership.objects.create(organization=org, user=admin, role=Membership.Role.ADMIN)
    stored = save_private_file(owner=owner, organization_id=org.pk, upload=png_upload())
    detail = reverse("stored-files-detail", kwargs={"org_id": org.pk, "pk": stored.pk})
    list_url = reverse("stored-files-list", kwargs={"org_id": org.pk})
    assert client_for(member).get(detail).status_code == 404
    assert client_for(admin).get(detail).status_code == 200
    with pytest.raises(NotFound):
        soft_delete_private_file(file=stored, actor=member, organization_id=org.pk)
    grant.is_active = False
    grant.save(update_fields=["is_active"])
    assert client_for(member).get(list_url).status_code == 404
    with pytest.raises(NotFound):
        save_private_file(owner=member, organization_id=org.pk, upload=png_upload())
    with patch(
        "apps.storage.services.resolve_file_scope",
        side_effect=[
            resolve_file_scope(user=owner, organization_id=org.pk),
            NotFound(),
        ],
    ):
        with pytest.raises(NotFound):
            save_private_file(owner=owner, organization_id=org.pk, upload=png_upload())
    assert StoredFile.objects.count() == 1
    assert sum(p.is_file() for p in private_disk.rglob("*")) == 1
    assert client_for(admin).delete(detail).status_code == 204
