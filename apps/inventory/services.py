# ruff: noqa: F401
"""Stable inventory services facade exposing the project-pinned schema mode."""

from django.conf import settings

if settings.INVENTORY_MODE == "tenant":
    from .tenant_services import execute_stock_operation
elif settings.INVENTORY_MODE == "standalone":
    from .standalone_services import execute_stock_operation
else:
    raise ValueError("Invalid INVENTORY_MODE; use tenant or standalone")
