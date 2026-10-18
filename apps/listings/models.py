"""Owner-private drafts and publicly readable, moderated classified ads."""

from django.conf import settings
from django.db import models

from apps.core.models import UUIDTimestampedModel


class ListingCategory(UUIDTimestampedModel):
    """Trusted staff-managed taxonomy, not per-user Catalog SKUs."""

    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=120)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("title",)


class Listing(UUIDTimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending moderation"
        PUBLISHED = "published", "Published"
        REJECTED = "rejected", "Rejected"
        ARCHIVED = "archived", "Archived"
        SOLD = "sold", "Sold"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    category = models.ForeignKey(ListingCategory, on_delete=models.PROTECT, related_name="+")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location_label = models.CharField(max_length=120, blank=True)
    price_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    attributes = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        permissions = [("moderate_listing", "Can approve or reject submitted listings")]
        indexes = [
            models.Index(fields=("status", "-published_at"), name="listings_public_idx"),
            models.Index(fields=("owner", "-created_at"), name="listings_owner_idx"),
        ]
