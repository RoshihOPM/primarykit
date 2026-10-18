from rest_framework import serializers

from .models import Deal


class DealSerializer(serializers.ModelSerializer):
    amount_minor = serializers.IntegerField(min_value=0, max_value=10**15)
    currency = serializers.RegexField(regex=r"^[A-Z]{3}$")

    class Meta:
        model = Deal
        fields = (
            "id",
            "title",
            "amount_minor",
            "currency",
            "notes",
            "stage",
            "version",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "stage", "version", "created_at", "updated_at")


class DealEditSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=0)
    title = serializers.CharField(max_length=200, required=False)
    amount_minor = serializers.IntegerField(min_value=0, max_value=10**15, required=False)
    currency = serializers.RegexField(regex=r"^[A-Z]{3}$", required=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=10000)


class DealTransitionSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=0)
    stage = serializers.ChoiceField(choices=Deal.Stage.choices)
