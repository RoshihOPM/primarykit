from rest_framework import serializers

from .models import Sale, SaleLineItem


class SaleLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleLineItem
        fields = ("sku", "title", "quantity", "unit_price_minor", "line_total_minor")


class SaleSerializer(serializers.ModelSerializer):
    lines = SaleLineSerializer(many=True, read_only=True)

    class Meta:
        model = Sale
        fields = (
            "id", "status", "currency", "total_minor", "source_order_id",
            "lines", "created_at", "voided_at",
        )


class RecordSaleSerializer(serializers.Serializer):
    currency = serializers.CharField(min_length=3, max_length=3)
    idempotency_key = serializers.CharField(min_length=8, max_length=128)
    source_order_id = serializers.UUIDField(required=False, allow_null=True)
    lines = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=100)
