"""Safe upload validation, blob persistence and transactional metadata creation."""

import hashlib
import logging
import uuid

from django.conf import settings
from django.core.files.storage import storages
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.core.audit import record_audit_event
from apps.organizations.models import Organization
from apps.organizations.permissions import get_active_membership
from apps.organizations.scoping import FULL_ACCESS, organization_scope

from .models import StoredFile

logger = logging.getLogger(__name__)

SIGNATURES = (
    ("image/png", (".png",)),
    ("image/jpeg", (".jpg", ".jpeg")),
    ("image/webp", (".webp",)),
    ("application/pdf", (".pdf",)),
)


class InvalidUpload(ValueError):
    pass


def _detect_content_type(head: bytes) -> str | None:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_upload(upload):
    max_size = settings.STORAGE_MAX_FILE_BYTES
    if not 0 < upload.size <= max_size:
        raise InvalidUpload("File is empty or exceeds the configured upload limit.")
    filename = (upload.name or "").replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    filename = filename.replace("\x00", "").replace("\r", "").replace("\n", "").strip()
    if not filename or len(filename) > 255:
        raise InvalidUpload("Invalid original file name.")
    first_bytes = upload.read(16)
    upload.seek(0)
    content_type = _detect_content_type(first_bytes)
    if not content_type or content_type not in settings.STORAGE_ALLOWED_MIME_TYPES:
        raise InvalidUpload("File type is not allowed.")
    valid_suffixes = dict(SIGNATURES)[content_type]
    if not filename.lower().endswith(valid_suffixes):
        raise InvalidUpload("File extension does not match file contents.")
    return filename, content_type


def _locked_scope(*, actor, organization_id):
    """Serialize organization membership updates and file mutations."""
    org = (
        Organization.objects.select_for_update().filter(pk=organization_id, is_active=True).first()
    )
    if org is None:
        raise NotFound()
    return org, get_active_membership(user=actor, organization=org)


def save_private_file(*, owner, organization, upload) -> StoredFile:
    """Verify membership twice and compensate a blob if persistence fails."""
    organization_scope(user=owner, org_id=organization.pk)
    filename, content_type = validate_upload(upload)
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    storage = storages["default"]
    requested_key = f"private/{organization.pk}/{uuid.uuid4().hex}"
    key = storage.save(requested_key, upload)
    try:
        with transaction.atomic():
            org, _ = _locked_scope(actor=owner, organization_id=organization.pk)
            file = StoredFile.objects.create(
                organization=org,
                owner=owner,
                object_key=key,
                original_name=filename,
                size=upload.size,
                content_type=content_type,
                sha256=digest.hexdigest(),
            )
            record_audit_event(
                actor=owner,
                action="storage.file.uploaded",
                target_type="storage.StoredFile",
                target_id=file.pk,
                changes={
                    "organization_id": str(org.pk),
                    "size": file.size,
                    "content_type": file.content_type,
                },
            )
    except Exception:
        try:
            storage.delete(key)
        except Exception:
            logger.exception("Could not clean up orphaned uploaded object")
        raise
    return file


@transaction.atomic
def soft_delete_private_file(*, file: StoredFile, actor, organization):
    org, membership = _locked_scope(actor=actor, organization_id=organization.pk)
    locked = (
        StoredFile.objects.select_for_update()
        .filter(pk=file.pk, organization=org, deleted_at__isnull=True)
        .first()
    )
    if locked is None or (locked.owner_id != actor.pk and membership.role not in FULL_ACCESS):
        raise NotFound()
    locked.deleted_at = timezone.now()
    locked.save(update_fields=["deleted_at"])
    record_audit_event(
        actor=actor,
        action="storage.file.deleted",
        target_type="storage.StoredFile",
        target_id=locked.pk,
        changes={"organization_id": str(org.pk)},
    )
    return True
