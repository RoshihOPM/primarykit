"""Private, sanitized listing photos with moderated, revocable public delivery.

Photo binaries never pass through apps.storage or its signed/private URLs.
"""
import io
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.core.audit import record_audit_event

from .models import Listing, ListingImage
from .services import StaleListing, _actor

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_EDGE = 2048
MAX_IMAGES = 8
MIME_TO_FORMAT = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}


def require_media():
    if not getattr(settings, "LISTINGS_MEDIA_ENABLED", False):
        raise NotFound()


def private_storage():
    """Dedicated storage alias, never the shared default/private Storage module."""
    return storages["listings_private"]


def media_url(image):
    return reverse(
        "listings-media-detail",
        kwargs={"listing_id": image.listing_id, "image_id": image.pk},
    )


def _clean_image(upload):
    """Decode actual image bytes, normalize orientation, remove metadata and re-encode."""
    if getattr(upload, "content_type", None) not in MIME_TO_FORMAT:
        raise ValidationError({"file": "Only JPEG, PNG or WebP photos are accepted."})
    raw = upload.read(MAX_UPLOAD_BYTES + 1)
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise ValidationError({"file": "Image must be non-empty and at most 5 MiB."})
    try:
        # Pillow is an explicit client-owned optional dependency (see docs/listings.md).
        from PIL import Image, ImageOps, UnidentifiedImageError

        with Image.open(io.BytesIO(raw)) as source:
            if source.format != MIME_TO_FORMAT[upload.content_type]:
                raise ValidationError({"file": "Declared media type does not match image bytes."})
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValidationError({"file": "Image dimensions exceed the pixel limit."})
            source.load()
            image = ImageOps.exif_transpose(source)
            if image.mode in ("RGBA", "P"):
                background = Image.new("RGB", image.size, "white")
                rgba = image.convert("RGBA")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=82, optimize=True)
            width, height = image.size
            return output.getvalue(), width, height
    except ImportError as exc:
        raise ValidationError({"file": "Install Pillow to enable listing photos."}) from exc
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValidationError({"file": "Invalid or unsafe image."}) from exc


def _owner_listing(*, actor, listing_id):
    user = _actor(actor)
    listing = Listing.objects.select_for_update().filter(pk=listing_id, owner=user).first()
    if listing is None:
        raise NotFound()
    return listing, user


def _expect_version(listing, expected_version):
    if type(expected_version) is not int or listing.version != expected_version:
        raise StaleListing()


def add_image(*, actor, listing_id, expected_version, uploaded):
    require_media()
    binary, width, height = _clean_image(uploaded)
    storage = private_storage()
    saved = None
    try:
        with transaction.atomic():
            listing, owner = _owner_listing(actor=actor, listing_id=listing_id)
            _expect_version(listing, expected_version)
            if listing.status not in {Listing.Status.DRAFT, Listing.Status.REJECTED}:
                raise ValidationError({"status": "Photos can be added to drafts or rejected ads."})
            if ListingImage.objects.filter(listing=listing).count() >= MAX_IMAGES:
                raise ValidationError({"file": "This ad already has the maximum of 8 photos."})
            saved = storage.save(f"listing-photos/{uuid.uuid4().hex}.jpg", ContentFile(binary))
            image = ListingImage.objects.create(
                listing=listing, private_key=saved, width=width, height=height,
                size_bytes=len(binary),
            )
            Listing.objects.filter(pk=listing.pk).update(
                version=F("version") + 1, updated_at=timezone.now()
            )
            record_audit_event(
                actor=owner, action="listings.media.uploaded",
                target_type="listings.ListingImage", target_id=image.pk,
            )
            return image
    except Exception:
        if saved is not None:
            # Rollback is not transactional for blob storage. Orphan sweeper is a backstop.
            storage.delete(saved)
        raise


def moderate_image(*, actor, listing_id, image_id, expected_version, decision):
    require_media()
    if decision not in {"approve", "reject"}:
        raise ValidationError({"decision": "Unsupported moderation decision."})
    user = _actor(actor)
    if not user.has_perm("listings.moderate_listing"):
        raise PermissionDenied("Moderation permission is required.")
    with transaction.atomic():
        listing = Listing.objects.select_for_update().filter(pk=listing_id).first()
        if listing is None:
            raise NotFound()
        if listing.owner_id == user.pk:
            raise PermissionDenied("Seller cannot review their own photos.")
        _expect_version(listing, expected_version)
        if listing.status != Listing.Status.PENDING:
            raise ValidationError({"status": "Photos can be moderated only on pending ads."})
        image = ListingImage.objects.select_for_update().filter(
            pk=image_id, listing=listing
        ).first()
        if image is None:
            raise NotFound()
        if image.status != ListingImage.Status.PENDING:
            raise ValidationError({"status": "Photo has already been reviewed."})
        image.status = (
            ListingImage.Status.APPROVED if decision == "approve"
            else ListingImage.Status.REJECTED
        )
        image.save(update_fields=("status", "updated_at"))
        Listing.objects.filter(pk=listing.pk).update(
            version=F("version") + 1, updated_at=timezone.now()
        )
        record_audit_event(
            actor=user, action=f"listings.media.{decision}",
            target_type="listings.ListingImage", target_id=image.pk,
        )
        return image


def remove_image(*, actor, listing_id, image_id, expected_version):
    require_media()
    with transaction.atomic():
        listing, owner = _owner_listing(actor=actor, listing_id=listing_id)
        _expect_version(listing, expected_version)
        if listing.status == Listing.Status.PENDING:
            raise ValidationError({"status": "Cannot remove photos during moderation."})
        image = ListingImage.objects.select_for_update().filter(
            pk=image_id, listing=listing
        ).first()
        if image is None:
            raise NotFound()
        key = image.private_key
        image.delete()
        Listing.objects.filter(pk=listing.pk).update(
            version=F("version") + 1, updated_at=timezone.now()
        )
        record_audit_event(
            actor=owner, action="listings.media.removed",
            target_type="listings.ListingImage", target_id=image_id,
        )
        # A deleted DB row is immediately inaccessible; object cleanup is best-effort.
        transaction.on_commit(lambda: private_storage().delete(key))


def visible_images(*, listing, actor):
    require_media()
    public = (
        listing.status == Listing.Status.PUBLISHED
        and listing.owner.is_active
        and listing.owner.email_verified
    )
    owner = (
        getattr(actor, "is_authenticated", False)
        and actor.pk == listing.owner_id
        and actor.is_active
        and actor.email_verified
    )
    moderator = (
        getattr(actor, "is_authenticated", False)
        and actor.is_active
        and actor.email_verified
        and actor.has_perm("listings.moderate_listing")
        and listing.status == Listing.Status.PENDING
    )
    if not (public or owner or moderator):
        raise NotFound()
    images = ListingImage.objects.filter(listing=listing).order_by("created_at", "pk")
    if not (owner or moderator):
        images = images.filter(status=ListingImage.Status.APPROVED)
    return images


def serialize_image(image):
    return {
        "id": str(image.pk),
        "status": image.status,
        "url": media_url(image),
        "width": image.width,
        "height": image.height,
    }
