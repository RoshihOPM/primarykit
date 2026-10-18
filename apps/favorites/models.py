"""Personal bookmarks and bounded saved searches, never globally readable."""

from django.conf import settings
from django.db import models

from apps.core.models import UUIDTimestampedModel


class Favorite(UUIDTimestampedModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    listing = models.ForeignKey(
        "listings.Listing", on_delete=models.CASCADE, related_name="+"
    )

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(fields=("owner", "listing"), name="fav_owner_listing_uniq")
        ]
        indexes = [models.Index(fields=("owner", "-created_at"), name="fav_owner_recent_idx")]


class SavedSearch(UUIDTimestampedModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField(max_length=80)
    filters = models.JSONField(default=dict)

    class Meta:
        ordering = ("-updated_at", "-id")
        indexes = [
            models.Index(fields=("owner", "-updated_at"), name="fav_search_recent_idx")
        ]
