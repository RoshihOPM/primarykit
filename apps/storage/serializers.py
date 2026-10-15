from rest_framework import serializers

from .models import StoredFile


class StoredFileReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoredFile
        fields = ("id", "original_name", "content_type", "size", "sha256", "created_at")
        read_only_fields = fields


class StoredFileUploadSerializer(serializers.Serializer):
    file = serializers.FileField(allow_empty_file=False, write_only=True)
