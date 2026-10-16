"""inventory serializers exports, selected by pinned project schema mode."""

from django.conf import settings

if settings.INVENTORY_MODE == "tenant":
    from .tenant_serializers import BalanceSerializer, InventoryOperationSerializer, ReservationSerializer, StockCommandSerializer, WarehouseSerializer
elif settings.INVENTORY_MODE == "standalone":
    from .standalone_serializers import (
        BalanceSerializer,
        InventoryItemSerializer,
        InventoryOperationSerializer,
        ReservationSerializer,
        StockCommandSerializer,
        WarehouseSerializer,
    )
else:
    raise ValueError("Invalid INVENTORY_MODE; use tenant or standalone")
