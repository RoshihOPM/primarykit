"""Owner-only commands: PostgreSQL constraints, row-locked search quotas."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.listings.models import Listing

from .domain import MAX_SAVED_SEARCHES, normalize_filters
from .models import Favorite, SavedSearch


def _actor(actor, *, lock=False):
    if not getattr(actor, "is_authenticated", False):
        raise NotFound()
    users = get_user_model().objects.filter(pk=actor.pk, is_active=True, email_verified=True)
    if lock:
        users = users.select_for_update()
    user = users.first()
    if user is None:
        raise NotFound()
    return user


def public_listings():
    """Mirror Listings v1 public scope; never include seller-owned private drafts."""
    return Listing.objects.filter(
        status=Listing.Status.PUBLISHED,
        owner__is_active=True,
        owner__email_verified=True,
    )


def visible_favorites(actor):
    user = _actor(actor)
    return (
        Favorite.objects.filter(
            owner=user,
            listing__status=Listing.Status.PUBLISHED,
            listing__owner__is_active=True,
            listing__owner__email_verified=True,
        )
        .select_related("listing", "listing__owner", "listing__category")
        .order_by("-created_at", "-id")
    )


@transaction.atomic
def add_favorite(*, actor, listing_id):
    user = _actor(actor)
    listing = public_listings().filter(pk=listing_id).first()
    if listing is None:
        raise NotFound()
    favorite, created = Favorite.objects.get_or_create(owner=user, listing=listing)
    return favorite, created


@transaction.atomic
def remove_favorite(*, actor, favorite_id):
    user = _actor(actor)
    deleted, _ = Favorite.objects.filter(pk=favorite_id, owner=user).delete()
    if not deleted:
        raise NotFound()


def owned_searches(actor):
    user = _actor(actor)
    return SavedSearch.objects.filter(owner=user).order_by("-updated_at", "-id")


@transaction.atomic
def create_search(*, actor, name, filters):
    user = _actor(actor, lock=True)
    if SavedSearch.objects.filter(owner=user).count() >= MAX_SAVED_SEARCHES:
        raise ValidationError({"searches": "Saved-search limit reached (20)."})
    try:
        normalized = normalize_filters(filters)
    except ValueError as exc:
        raise ValidationError({"filters": str(exc)}) from exc
    return SavedSearch.objects.create(owner=user, name=name, filters=normalized)


@transaction.atomic
def update_search(*, actor, search_id, changes):
    user = _actor(actor)
    search = SavedSearch.objects.select_for_update().filter(owner=user, pk=search_id).first()
    if search is None:
        raise NotFound()
    if not changes:
        raise ValidationError({"search": "At least one change is required."})
    if "filters" in changes:
        try:
            search.filters = normalize_filters(changes["filters"])
        except ValueError as exc:
            raise ValidationError({"filters": str(exc)}) from exc
    if "name" in changes:
        search.name = changes["name"]
    search.updated_at = timezone.now()
    search.save(update_fields=("name", "filters", "updated_at"))
    return search


@transaction.atomic
def delete_search(*, actor, search_id):
    user = _actor(actor)
    deleted, _ = SavedSearch.objects.filter(owner=user, pk=search_id).delete()
    if not deleted:
        raise NotFound()
