from rest_framework import serializers

from .models import AttributeDefinition, CatalogItem, Category
from .services import validate_attributes


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "slug", "name", "is_active")
        read_only_fields = ("id",)


class AttributeDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeDefinition
        fields = ("id", "category", "code", "data_type", "required")
        read_only_fields = ("id",)

    def validate_category(self, value):
        if not value.is_active:
            raise serializers.ValidationError("Inactive categories cannot be extended.")
        return value


class CatalogItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogItem
        fields = ("id", "sku", "category", "name", "description", "attributes", "is_active")
        read_only_fields = ("id",)

    def validate(self, attrs):
        category = attrs.get("category", getattr(self.instance, "category", None))
        if category is None:
            return attrs
        if self.instance is None and not category.is_active:
            raise serializers.ValidationError({"category": "Category must be active."})
        values = attrs.get("attributes", getattr(self.instance, "attributes", {}))
        # Changing the category always validates against its new definitions.
        attrs["attributes"] = validate_attributes(category, values)
        return attrs

    def validate_sku(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("SKU cannot be empty.")
        return value
