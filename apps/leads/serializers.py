from django.contrib.auth import get_user_model
from rest_framework import serializers

from .services import validate_assignee

from .models import Lead


class LeadSerializer(serializers.ModelSerializer):
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(is_active=True),
        allow_null=True, required=False,
    )

    def validate_assigned_to(self, assignee):
        validate_assignee(actor=self.context["request"].user, assignee=assignee)
        return assignee

    class Meta:
        model = Lead
        fields = (
            "id",
            "title",
            "contact_name",
            "assigned_to",
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


class LeadEditSerializer(serializers.ModelSerializer):
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(is_active=True),
        allow_null=True, required=False,
    )
    expected_version = serializers.IntegerField(min_value=0)

    class Meta:
        model = Lead
        fields = (
            "expected_version",
            "assigned_to",
            "title",
            "contact_name",
            "contact_email",
            "contact_phone",
            "source",
            "notes",
        )
        extra_kwargs = {
            field: {"required": False}
            for field in (
                "assigned_to",
                "title",
                "contact_name",
                "contact_email",
                "contact_phone",
                "source",
                "notes",
            )
        }


class LeadTransitionSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=0)
    status = serializers.ChoiceField(choices=Lead.Status.choices)
