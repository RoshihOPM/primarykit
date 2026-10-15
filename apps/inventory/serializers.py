from rest_framework import serializers

from apps.catalog.models import CatalogItem

from .models import InventoryOperation, StockBalance, StockReservation, Warehouse


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ("id", "code", "name", "is_active")
        read_only_fields = ("id",)


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
    KINDS = ("receive", "issue", "transfer", "reserve", "release", "consume")
    kind = serializers.ChoiceField(choices=KINDS)
    idempotency_key = serializers.CharField(max_length=128, min_length=8, trim_whitespace=True)
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all(), required=False)
    destination = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all(), required=False)
    item = serializers.PrimaryKeyRelatedField(queryset=CatalogItem.objects.all(), required=False)
    quantity = serializers.IntegerField(min_value=1, max_value=10**12, required=False)
    reservation = serializers.PrimaryKeyRelatedField(queryset=StockReservation.objects.all(), required=False)

    def validate(self, attrs):
        kind = attrs["kind"]
        if kind in {"release", "consume"}:
            required = {"reservation"}
            forbidden = {"warehouse", "destination", "item", "quantity"}
        else:
            required = {"warehouse", "item", "quantity"}
            forbidden = {"reservation"}
            if kind == "transfer":
                required.add("destination")
            else:
                forbidden.add("destination")
        absent = required - attrs.keys()
        unexpected = forbidden & attrs.keys()
        if absent or unexpected:
            raise serializers.ValidationError(
                {"detail": "Invalid fields for this stock operation."}
            )
        return attrs
