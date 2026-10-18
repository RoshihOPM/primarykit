from rest_framework import serializers

from .models import Lead


class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = (
            "id",
            "title",
            "contact_name",
            "contact_email",
            "contact_phone",
            "source",
            "notes",
            "status",
            "version",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "status", "version", "created_at", "updated_at")


class LeadTransitionSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=0)
    status = serializers.ChoiceField(choices=Lead.Status.choices)
