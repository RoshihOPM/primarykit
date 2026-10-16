"""Standalone Catalog persistence. Files copied without Organizations remain owner-private."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import UUIDTimestampedModel

from .domain import normalize_sku


class Category(UUIDTimestampedModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    slug = models.SlugField(max_length=80)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=("owner", "slug"), name="catalog_owner_category_slug")
        ]

    def __str__(self):
        return self.name


class AttributeDefinition(UUIDTimestampedModel):
    class DataType(models.TextChoices):
        TEXT = "text", "Text"
        INTEGER = "integer", "Integer"
        DECIMAL = "decimal", "Decimal"
        BOOLEAN = "boolean", "Boolean"

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="definitions")
    code = models.SlugField(max_length=80)
    data_type = models.CharField(max_length=12, choices=DataType.choices)
    required = models.BooleanField(default=False)

    class Meta:
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(fields=("category", "code"), name="catalog_attribute_code_uniq")
        ]


class CatalogItem(UUIDTimestampedModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    category = models.ForeignKey(Category, related_name="items", on_delete=models.PROTECT)
    sku = models.CharField(max_length=80)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name", "sku")
        constraints = [
            models.UniqueConstraint(Lower("sku"), "owner", name="catalog_owner_sku_ci_uniq"),
        ]
        indexes = [
            models.Index(fields=["owner", "category", "is_active"], name="catalog_owner_cat_idx")
        ]

    def save(self, *args, **kwargs):
        self.sku = normalize_sku(self.sku)
        if self.category_id and self.owner_id:
            category_owner = (
                Category.objects.filter(pk=self.category_id)
                .values_list("owner_id", flat=True)
                .first()
            )
            if category_owner != self.owner_id:
                raise ValidationError("Item and category must have the same owner.")
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sku}: {self.name}"
