"""HTTP adapter for standalone owner-scoped Catalog."""

from rest_framework import serializers

from .domain import CatalogRuleViolation, normalize_sku
from .models import AttributeDefinition, CatalogItem, Category
from .services import validate_attributes


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "slug", "name", "is_active")
        read_only_fields = ("id",)

    def validate_slug(self, value):
        actor = self.context["request"].user
        if (
            Category.objects.filter(owner=actor, slug=value)
            .exclude(pk=getattr(self.instance, "pk", None))
            .exists()
        ):
            raise serializers.ValidationError("Category slug already exists.")
        return value


class AttributeDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeDefinition
        fields = ("id", "category", "code", "data_type", "required")
        read_only_fields = ("id",)

    def get_fields(self):
        fields = super().get_fields()
        fields["category"].queryset = Category.objects.filter(owner=self.context["request"].user)
        return fields

    def validate_category(self, value):
        if not value.is_active:
            raise serializers.ValidationError("Inactive categories cannot be extended.")
        return value


class CatalogItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogItem
        fields = ("id", "sku", "category", "name", "description", "attributes", "is_active")
        read_only_fields = ("id",)

    def get_fields(self):
        fields = super().get_fields()
        fields["category"].queryset = Category.objects.filter(owner=self.context["request"].user)
        return fields

    def validate(self, attrs):
        category = attrs.get("category", getattr(self.instance, "category", None))
        if category is None:
            return attrs
        if category.owner_id != self.context["request"].user.pk:
            raise serializers.ValidationError({"category": "Wrong owner."})
        if self.instance is None and not category.is_active:
            raise serializers.ValidationError({"category": "Category must be active."})
        attrs["attributes"] = validate_attributes(
            category, attrs.get("attributes", getattr(self.instance, "attributes", {}))
        )
        return attrs

    def validate_sku(self, value):
        try:
            normalized = normalize_sku(value)
        except CatalogRuleViolation as exc:
            raise serializers.ValidationError(str(exc)) from exc
        if (
            CatalogItem.objects.filter(owner=self.context["request"].user, sku__iexact=normalized)
            .exclude(pk=getattr(self.instance, "pk", None))
            .exists()
        ):
            raise serializers.ValidationError("SKU already exists.")
        return normalized
