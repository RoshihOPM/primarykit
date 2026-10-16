from rest_framework import serializers

from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ("sku", "title", "quantity", "unit_price_minor", "line_total_minor")


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "status",
            "currency",
            "total_minor",
            "items",
            "created_at",
            "canceled_at",
        )


class PlaceOrderSerializer(serializers.Serializer):
    currency = serializers.CharField(min_length=3, max_length=3)
    idempotency_key = serializers.CharField(min_length=8, max_length=128)
    lines = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=100)
