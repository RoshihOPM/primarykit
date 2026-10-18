"""Transactional listing commands. No global superuser owner override."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from apps.core.audit import record_audit_event

from .domain import ListingRuleError, next_status, normalize_fields
from .models import Listing, ListingCategory

EDITABLE_FIELDS = frozenset(
    {"category", "title", "description", "location_label", "price_minor", "currency", "attributes"}
)


class StaleListing(APIException):
    status_code = 409
    default_detail = "Listing version changed. Refresh before retrying."
    default_code = "stale_listing"


def _actor(actor):
    if not getattr(actor, "is_authenticated", False):
        raise NotFound()
    user = get_user_model().objects.filter(pk=actor.pk, is_active=True, email_verified=True).first()
    if user is None:
        raise NotFound()
    return user


def _category(category):
    if not isinstance(category, ListingCategory):
        raise ValidationError({"category": "Unknown category."})
    if not ListingCategory.objects.filter(pk=category.pk, active=True).exists():
        raise ValidationError({"category": "Inactive or unknown category."})
    return category


@transaction.atomic
def create_listing(*, actor, fields: dict) -> Listing:
    owner = _actor(actor)
    category = _category(fields["category"])
    try:
        values = normalize_fields(fields)
    except ListingRuleError as exc:
        raise ValidationError({"listing": str(exc)}) from exc
    listing = Listing.objects.create(owner=owner, category=category, **values)
    record_audit_event(
        actor=owner, action="listings.created", target_type="listings.Listing", target_id=listing.pk
    )
    return listing


@transaction.atomic
def edit_listing(*, actor, listing_id, expected_version: int, changes: dict) -> Listing:
    owner = _actor(actor)
    listing = Listing.objects.select_for_update().filter(pk=listing_id, owner=owner).first()
    if listing is None:
        raise NotFound()
    if type(expected_version) is not int or expected_version != listing.version:
        raise StaleListing()
    if listing.status not in {Listing.Status.DRAFT, Listing.Status.REJECTED}:
        raise ValidationError({"status": "Only draft/rejected listings can be edited."})
    if not changes or set(changes) - EDITABLE_FIELDS:
        raise ValidationError({"listing": "Expected one or more editable fields."})
    category = _category(changes.get("category", listing.category))
    fields = {name: getattr(listing, name) for name in EDITABLE_FIELDS - {"category"}}
    fields.update({name: value for name, value in changes.items() if name != "category"})
    try:
        normalized = normalize_fields(fields)
    except ListingRuleError as exc:
        raise ValidationError({"listing": str(exc)}) from exc
    count = Listing.objects.filter(
        pk=listing.pk, owner=owner, version=expected_version, status=listing.status
    ).update(
        **normalized, category=category, version=expected_version + 1, updated_at=timezone.now()
    )
    if not count:
        raise StaleListing()
    listing.refresh_from_db()
    record_audit_event(
        actor=owner, action="listings.edited", target_type="listings.Listing", target_id=listing.pk
    )
    return listing


@transaction.atomic
def transition_listing(*, actor, listing_id, expected_version: int, action: str) -> Listing:
    user = _actor(actor)
    moderator = action in {"approve", "reject"}
    if moderator and not user.has_perm("listings.moderate_listing"):
        raise PermissionDenied("Moderation permission is required.")
    qs = Listing.objects.select_for_update()
    if not moderator:
        qs = qs.filter(owner=user)
    listing = qs.filter(pk=listing_id).first()
    if listing is None:
        raise NotFound()
    if type(expected_version) is not int or expected_version != listing.version:
        raise StaleListing()
    if moderator and listing.owner_id == user.pk:
        raise PermissionDenied("Seller cannot moderate their own listing.")
    if not moderator and action not in {"submit", "archive", "mark_sold"}:
        raise PermissionDenied()
    if action in {"submit", "approve"}:
        _category(listing.category)
    if action == "approve" and not get_user_model().objects.filter(
        pk=listing.owner_id, is_active=True, email_verified=True
    ).exists():
        raise ValidationError({"owner": "Seller is no longer eligible for publication."})
    try:
        status = next_status(listing.status, action)
    except ListingRuleError as exc:
        raise ValidationError({"status": str(exc)}) from exc
    updated = {"status": status, "version": expected_version + 1, "updated_at": timezone.now()}
    if status == "published":
        updated["published_at"] = timezone.now()
    if status in {"archived", "sold"}:
        updated["closed_at"] = timezone.now()
    count = Listing.objects.filter(
        pk=listing.pk, version=expected_version, status=listing.status
    ).update(**updated)
    if not count:
        raise StaleListing()
    listing.refresh_from_db()
    record_audit_event(
        actor=user,
        action=f"listings.{action}",
        target_type="listings.Listing",
        target_id=listing.pk,
    )
    return listing
