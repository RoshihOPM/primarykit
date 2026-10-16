"""inventory views exports, selected by pinned project schema mode."""

from django.conf import settings

if settings.INVENTORY_MODE == "tenant":
    from .tenant_views import BalanceViewSet, OperationViewSet, ReservationViewSet, WarehouseViewSet
elif settings.INVENTORY_MODE == "standalone":
    from .standalone_views import BalanceViewSet, OperationViewSet, ReservationViewSet, WarehouseViewSet
else:
    raise ValueError("Invalid INVENTORY_MODE; use tenant or standalone")
