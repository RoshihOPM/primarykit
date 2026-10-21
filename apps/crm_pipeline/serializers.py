from rest_framework import serializers

from .models import DealCardLink


class BindDealCardSerializer(serializers.Serializer):
    deal_id = serializers.UUIDField()
    card_id = serializers.UUIDField()


class DealCardLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DealCardLink
        fields = ("id", "deal_id", "card_id", "created_at")
        read_only_fields = fields
