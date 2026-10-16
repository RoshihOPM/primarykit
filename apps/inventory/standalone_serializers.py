"""Personal Inventory REST input: every foreign identifier belongs to the actor."""

from rest_framework import serializers

from .domain import COMMAND_KINDS, StockRuleViolation, validate_command_shape
from .models import InventoryItem, InventoryOperation, StockBalance, StockReservation, Warehouse


class InventoryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryItem
        fields = ("id", "sku", "name", "is_active")
        read_only_fields = ("id",)

    def validate_sku(self, value):
        sku = value.strip().upper()
        if not sku:
            raise serializers.ValidationError("SKU cannot be empty.")
        if (
            InventoryItem.objects.filter(owner=self.context["request"].user, sku__iexact=sku)
            .exclude(pk=getattr(self.instance, "pk", None))
            .exists()
        ):
            raise serializers.ValidationError("SKU already exists.")
        return sku


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ("id", "code", "name", "is_active")
        read_only_fields = ("id",)

    def validate_code(self, value):
        if (
            Warehouse.objects.filter(owner=self.context["request"].user, code=value)
            .exclude(pk=getattr(self.instance, "pk", None))
            .exists()
        ):
            raise serializers.ValidationError("Warehouse code already exists.")
        return value


class BalanceSerializer(serializers.ModelSerializer):
    available = serializers.IntegerField(read_only=True)

    class Meta:
        model = StockBalance
        fields = ("id", "warehouse", "item", "on_hand", "reserved", "available")
        read_only_fields = fields


class ReservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockReservation
        fields = ("id", "balance", "quantity", "status", "created_by", "created_at", "closed_at")
        read_only_fields = fields


class InventoryOperationSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryOperation
        fields = ("id", "kind", "created_at", "result")
        read_only_fields = fields


class StockCommandSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=COMMAND_KINDS)
    idempotency_key = serializers.CharField(max_length=128, min_length=8, trim_whitespace=True)
    warehouse = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.none(), required=False
    )
    destination = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.none(), required=False
    )
    item = serializers.PrimaryKeyRelatedField(queryset=InventoryItem.objects.none(), required=False)
    quantity = serializers.IntegerField(min_value=1, max_value=10**12, required=False)
    reservation = serializers.PrimaryKeyRelatedField(
        queryset=StockReservation.objects.none(), required=False
    )

    def get_fields(self):
        fields = super().get_fields()
        actor = self.context["request"].user
        warehouses = Warehouse.objects.filter(owner=actor, is_active=True)
        fields["warehouse"].queryset = warehouses
        fields["destination"].queryset = warehouses
        fields["item"].queryset = InventoryItem.objects.filter(owner=actor, is_active=True)
        fields["reservation"].queryset = StockReservation.objects.filter(balance__owner=actor)
        return fields

    def validate(self, attrs):
        try:
            validate_command_shape(attrs["kind"], attrs)
        except StockRuleViolation as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return attrs
