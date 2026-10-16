"""inventory services exports, selected by pinned project schema mode."""

from django.conf import settings

if settings.INVENTORY_MODE == "tenant":
    from .tenant_services import execute_stock_operation
elif settings.INVENTORY_MODE == "standalone":
    from .standalone_services import execute_stock_operation
else:
    raise ValueError("Invalid INVENTORY_MODE; use tenant or standalone")
