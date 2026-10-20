from rest_framework import serializers

from .models import Contact


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = (
            "id",
            "name",
            "email",
            "phone",
            "company",
            "notes",
            "version",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "version", "created_at", "updated_at")


class ContactEditSerializer(serializers.ModelSerializer):
    expected_version = serializers.IntegerField(min_value=0)

    class Meta:
        model = Contact
        fields = ("expected_version", "name", "email", "phone", "company", "notes")
        extra_kwargs = {
            "name": {"required": False},
            "email": {"required": False},
            "phone": {"required": False},
            "company": {"required": False},
            "notes": {"required": False},
        }
