from rest_framework import serializers

from .models import Lead


class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = (
            "id", "title", "contact_name", "contact_email", "contact_phone",
            "source", "notes", "status", "version", "created_at", "updated_at",
        )
        read_only_fields = ("id", "status", "version", "created_at", "updated_at")


class LeadEditSerializer(serializers.ModelSerializer):
    expected_version = serializers.IntegerField(min_value=0)

    class Meta:
        model = Lead
        fields = (
            "expected_version", "title", "contact_name", "contact_email",
            "contact_phone", "source", "notes",
        )
        extra_kwargs = {
            field: {"required": False}
            for field in ("title", "contact_name", "contact_email", "contact_phone", "source", "notes")
        }


class LeadTransitionSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=0)
    status = serializers.ChoiceField(choices=Lead.Status.choices)
