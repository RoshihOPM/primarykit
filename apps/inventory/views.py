# ruff: noqa: F401
"""Stable inventory views facade exposing the project-pinned schema mode."""

from django.conf import settings

if settings.INVENTORY_MODE == "tenant":
    from .tenant_views import (
        BalanceViewSet,
        OperationViewSet,
        ReservationViewSet,
        WarehouseViewSet,
    )
elif settings.INVENTORY_MODE == "standalone":
    from .standalone_views import (
        BalanceViewSet,
        OperationViewSet,
        ReservationViewSet,
        WarehouseViewSet,
    )
else:
    raise ValueError("Invalid INVENTORY_MODE; use tenant or standalone")
