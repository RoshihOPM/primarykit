"""Organization-scoped category definitions and catalog items."""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import UUIDTimestampedModel
from apps.organizations.models import Organization


class Category(UUIDTimestampedModel):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="catalog_categories"
    )
    slug = models.SlugField(max_length=80)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "slug"), name="catalog_category_org_slug_uniq"
            )
        ]

    def __str__(self):
        return self.name


class AttributeDefinition(UUIDTimestampedModel):
    class DataType(models.TextChoices):
        TEXT = "text", "Text"
        INTEGER = "integer", "Integer"
        DECIMAL = "decimal", "Decimal"
        BOOLEAN = "boolean", "Boolean"

    category = models.ForeignKey(Category, related_name="definitions", on_delete=models.PROTECT)
    code = models.SlugField(max_length=80)
    data_type = models.CharField(max_length=12, choices=DataType.choices)
    required = models.BooleanField(default=False)

    class Meta:
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(
                fields=("category", "code"), name="catalog_attribute_code_uniq"
            ),
        ]


class CatalogItem(UUIDTimestampedModel):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="catalog_items"
    )
    category = models.ForeignKey(Category, related_name="items", on_delete=models.PROTECT)
    sku = models.CharField(max_length=80)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name", "sku")
        constraints = [
            models.UniqueConstraint(
                Lower("sku"), "organization", name="catalog_org_sku_ci_uniq"
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "category", "is_active"], name="catalog_org_category_idx")
        ]

    def save(self, *args, **kwargs):
        self.sku = self.sku.strip().upper()
        if self.category_id and self.organization_id:
            category_org = Category.objects.filter(pk=self.category_id).values_list(
                "organization_id", flat=True
            ).first()
            if category_org != self.organization_id:
                raise ValidationError("Catalog item category must belong to the same organization.")
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sku}: {self.name}"
