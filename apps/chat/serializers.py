from rest_framework import serializers

from .models import Dialogue, Message


class DialogueCreateSerializer(serializers.Serializer):
    recipient_id = serializers.UUIDField()
    organization_id = serializers.UUIDField(required=False, allow_null=True)


class DialogueReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dialogue
        fields = (
            "id",
            "user_low",
            "user_high",
            "organization_id",
            "last_sequence",
            "low_read_sequence",
            "high_read_sequence",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class MessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    attachment_id = serializers.UUIDField(required=False, allow_null=True)


class MessageReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ("id", "sequence", "sender", "body", "attachment_id", "created_at")
        read_only_fields = fields


class ReadReceiptSerializer(serializers.Serializer):
    sequence = serializers.IntegerField(min_value=0)
