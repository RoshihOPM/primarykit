from rest_framework import serializers

from .models import PaymentIntent


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentIntent
        fields = (
            "id", "amount_minor", "currency", "status", "source_order_id",
            "created_at", "settled_at",
        )


class CreatePaymentSerializer(serializers.Serializer):
    amount_minor = serializers.IntegerField(min_value=1, max_value=9_000_000_000_000_000)
    currency = serializers.CharField(min_length=3, max_length=3)
    idempotency_key = serializers.CharField(min_length=8, max_length=128)
    source_order_id = serializers.UUIDField(required=False, allow_null=True)


class ManualReconciliationSerializer(serializers.Serializer):
    event_key = serializers.CharField(min_length=8, max_length=128)
    outcome = serializers.ChoiceField(choices=("succeeded", "failed"))
    amount_minor = serializers.IntegerField(min_value=1, max_value=9_000_000_000_000_000)
    currency = serializers.CharField(min_length=3, max_length=3)
