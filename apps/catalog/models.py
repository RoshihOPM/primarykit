"""Business-neutral catalog. Domain-specific fields belong in dedicated apps."""

from django.db import models
from django.db.models.functions import Lower

from apps.core.models import UUIDTimestampedModel


class Category(UUIDTimestampedModel):
    slug = models.SlugField(unique=True, max_length=80)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class AttributeDefinition(UUIDTimestampedModel):
    class DataType(models.TextChoices):
        TEXT = "text", "Text"
        INTEGER = "integer", "Integer"
        DECIMAL = "decimal", "Decimal"
        BOOLEAN = "boolean", "Boolean"

    category = models.ForeignKey(
        Category, related_name="definitions", on_delete=models.PROTECT
    )
    code = models.SlugField(max_length=80)
    data_type = models.CharField(max_length=12, choices=DataType.choices)
    required = models.BooleanField(default=False)

    class Meta:
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(fields=("category", "code"), name="catalog_attribute_code_uniq"),
        ]


class CatalogItem(UUIDTimestampedModel):
    category = models.ForeignKey(
        Category, related_name="items", on_delete=models.PROTECT
    )
    sku = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name", "sku")
        constraints = [
            models.UniqueConstraint(Lower("sku"), name="catalog_sku_case_insensitive_uniq"),
        ]
        indexes = [models.Index(fields=["category", "is_active"], name="catalog_category_active_idx")]

    def save(self, *args, **kwargs):
        self.sku = self.sku.strip().upper()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sku}: {self.name}"
