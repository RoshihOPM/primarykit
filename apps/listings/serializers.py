from rest_framework import serializers

from .models import Listing, ListingCategory


class ListingCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingCategory
        fields = ("id", "slug", "title")


class ListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Listing
        fields = (
            "id",
            "owner",
            "category",
            "title",
            "description",
            "location_label",
            "price_minor",
            "currency",
            "attributes",
            "status",
            "version",
            "created_at",
            "updated_at",
            "published_at",
            "closed_at",
        )
        read_only_fields = fields


class EditableFieldsSerializer(serializers.Serializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=ListingCategory.objects.filter(active=True), required=False
    )
    title = serializers.CharField(max_length=200, required=False, trim_whitespace=True)
    description = serializers.CharField(
        max_length=10000, required=False, allow_blank=True, trim_whitespace=False
    )
    location_label = serializers.CharField(max_length=120, required=False, allow_blank=True)
    price_minor = serializers.IntegerField(min_value=0, max_value=10**15, required=False)
    currency = serializers.RegexField(regex=r"^[A-Z]{3}$", required=False)
    attributes = serializers.JSONField(required=False)


class CreateListingSerializer(EditableFieldsSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=ListingCategory.objects.filter(active=True)
    )
    title = serializers.CharField(min_length=3, max_length=200, trim_whitespace=True)
    price_minor = serializers.IntegerField(min_value=0, max_value=10**15)
    currency = serializers.RegexField(regex=r"^[A-Z]{3}$")


class EditListingSerializer(EditableFieldsSerializer):
    expected_version = serializers.IntegerField(min_value=0)


class VersionSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=0)


class ModerateSerializer(VersionSerializer):
    decision = serializers.ChoiceField(choices=("approve", "reject"))
