"""inventory models exports, selected by pinned project schema mode."""

from django.conf import settings

if settings.INVENTORY_MODE == "tenant":
    from .tenant_models import InventoryOperation, StockBalance, StockMovement, StockReservation, Warehouse
elif settings.INVENTORY_MODE == "standalone":
    from .standalone_models import InventoryOperation, StockBalance, StockMovement, StockReservation, Warehouse
else:
    raise ValueError("Invalid INVENTORY_MODE; use tenant or standalone")
