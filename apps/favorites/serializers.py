from rest_framework import serializers

from apps.listings.serializers import ListingSerializer

from .domain import normalize_filters
from .models import Favorite, SavedSearch


class FavoriteCreateSerializer(serializers.Serializer):
    listing_id = serializers.UUIDField()

    def validate(self, attrs):
        if set(self.initial_data) != {"listing_id"}:
            raise serializers.ValidationError("Only listing_id is accepted.")
        return attrs


class FavoriteReadSerializer(serializers.ModelSerializer):
    listing = ListingSerializer(read_only=True)

    class Meta:
        model = Favorite
        fields = ("id", "listing", "created_at")
        read_only_fields = fields


class SavedSearchWriteSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=80, trim_whitespace=True)
    filters = serializers.JSONField()

    def validate_filters(self, value):
        try:
            return normalize_filters(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs):
        if set(self.initial_data) - {"name", "filters"}:
            raise serializers.ValidationError("Only name and filters are accepted.")
        if not attrs:
            raise serializers.ValidationError("At least one field is required.")
        return attrs


class SavedSearchReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedSearch
        fields = ("id", "name", "filters", "created_at", "updated_at")
        read_only_fields = fields
