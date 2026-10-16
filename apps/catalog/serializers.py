from rest_framework import serializers

from .models import AttributeDefinition, CatalogItem, Category
from .services import validate_attributes


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "organization", "slug", "name", "is_active")
        read_only_fields = ("id", "organization")

    def validate_slug(self, value):
        org = self.context["view"].get_scope()[0]
        if Category.objects.filter(organization=org, slug=value).exclude(
            pk=getattr(self.instance, "pk", None)
        ).exists():
            raise serializers.ValidationError("Category slug already exists in this organization.")
        return value


class AttributeDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeDefinition
        fields = ("id", "category", "code", "data_type", "required")
        read_only_fields = ("id",)

    def get_fields(self):
        fields = super().get_fields()
        org = self.context["view"].get_scope()[0]
        fields["category"].queryset = Category.objects.filter(organization=org)
        return fields

    def validate_category(self, value):
        if not value.is_active:
            raise serializers.ValidationError("Inactive categories cannot be extended.")
        return value


class CatalogItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogItem
        fields = (
            "id", "organization", "sku", "category", "name",
            "description", "attributes", "is_active",
        )
        read_only_fields = ("id", "organization")

    def get_fields(self):
        fields = super().get_fields()
        org = self.context["view"].get_scope()[0]
        fields["category"].queryset = Category.objects.filter(organization=org)
        return fields

    def validate(self, attrs):
        category = attrs.get("category", getattr(self.instance, "category", None))
        if category is None:
            return attrs
        org = self.context["view"].get_scope()[0]
        if category.organization_id != org.pk:
            raise serializers.ValidationError({"category": "Wrong organization."})
        if self.instance is None and not category.is_active:
            raise serializers.ValidationError({"category": "Category must be active."})
        values = attrs.get("attributes", getattr(self.instance, "attributes", {}))
        attrs["attributes"] = validate_attributes(category, values)
        return attrs

    def validate_sku(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("SKU cannot be empty.")
        org = self.context["view"].get_scope()[0]
        if CatalogItem.objects.filter(organization=org, sku__iexact=value).exclude(
            pk=getattr(self.instance, "pk", None)
        ).exists():
            raise serializers.ValidationError("SKU already exists in this organization.")
        return value
