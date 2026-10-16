"""All foreign-key inputs are scoped before validation (including write endpoints)."""

from rest_framework import serializers

from apps.catalog.models import CatalogItem
from apps.organizations.models import Branch

from .models import InventoryOperation, StockBalance, StockReservation, Warehouse


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ("id", "organization", "branch", "code", "name", "is_active")
        read_only_fields = ("id", "organization")

    def get_fields(self):
        fields = super().get_fields()
        organization, membership = self.context["view"].get_scope()
        qs = Branch.objects.filter(organization=organization, is_active=True)
        if membership.role not in ("owner", "admin"):
            from apps.organizations.scoping import branch_ids_for

            qs = qs.filter(pk__in=branch_ids_for(membership))
        fields["branch"].queryset = qs
        return fields

    def validate_code(self, value):
        org = self.context["view"].get_scope()[0]
        if (
            Warehouse.objects.filter(organization=org, code=value)
            .exclude(pk=getattr(self.instance, "pk", None))
            .exists()
        ):
            raise serializers.ValidationError("Warehouse code already exists in this company.")
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
    KINDS = ("receive", "issue", "transfer", "reserve", "release", "consume")
    kind = serializers.ChoiceField(choices=KINDS)
    idempotency_key = serializers.CharField(max_length=128, min_length=8, trim_whitespace=True)
    warehouse = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.none(), required=False
    )
    destination = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.none(), required=False
    )
    item = serializers.PrimaryKeyRelatedField(queryset=CatalogItem.objects.none(), required=False)
    quantity = serializers.IntegerField(min_value=1, max_value=10**12, required=False)
    reservation = serializers.PrimaryKeyRelatedField(
        queryset=StockReservation.objects.none(), required=False
    )

    def get_fields(self):
        fields = super().get_fields()
        organization, membership = self.context["view"].get_scope()
        from apps.organizations.scoping import branch_ids_for

        warehouses = Warehouse.objects.filter(
            organization=organization, is_active=True, branch__is_active=True
        )
        if membership.role not in ("owner", "admin"):
            warehouses = warehouses.filter(branch_id__in=branch_ids_for(membership))
        for field in ("warehouse", "destination"):
            fields[field].queryset = warehouses
        fields["item"].queryset = CatalogItem.objects.filter(
            organization=organization, is_active=True, category__is_active=True
        )
        # Closing a reservation must still work after a warehouse is deactivated.
        close_warehouses = Warehouse.objects.filter(organization=organization)
        if membership.role not in ("owner", "admin"):
            from apps.organizations.models import BranchAccess

            close_warehouses = close_warehouses.filter(
                branch_id__in=BranchAccess.objects.filter(
                    membership=membership, branch__organization=organization
                ).values_list("branch_id", flat=True)
            )
        fields["reservation"].queryset = StockReservation.objects.filter(
            balance__organization=organization,
            balance__warehouse__in=close_warehouses,
        )
        return fields

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
        if required - attrs.keys() or forbidden & attrs.keys():
            raise serializers.ValidationError(
                {"detail": "Invalid fields for this stock operation."}
            )
        return attrs
