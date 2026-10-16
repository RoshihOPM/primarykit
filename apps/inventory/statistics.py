"""Inventory owns current stock/warehouse and period operation metrics."""

from django.conf import settings
from django.db.models import Sum

from apps.statistics.domain import Metric, Provider

from .models import InventoryOperation, StockBalance, Warehouse


def _scope(context):
    if settings.INVENTORY_MODE == "standalone":
        return {"owner": context.actor}
    return {"organization": context.organization}


def _warehouses(context):
    return Warehouse.objects.filter(**_scope(context)).count()


def _on_hand(context):
    return StockBalance.objects.filter(**_scope(context)).aggregate(value=Sum("on_hand"))["value"] or 0


def _reserved(context):
    return StockBalance.objects.filter(**_scope(context)).aggregate(value=Sum("reserved"))["value"] or 0


def _operations(context):
    return InventoryOperation.objects.filter(
        **_scope(context), created_at__gte=context.since, created_at__lt=context.until
    ).count()


_scopes = ("personal",) if settings.INVENTORY_MODE == "standalone" else ("tenant",)
PROVIDER = Provider(
    code="inventory",
    metrics=(
        Metric("warehouses", "Warehouses", "count", "snapshot", _scopes, _warehouses),
        Metric("on_hand", "Quantity on hand", "units", "snapshot", _scopes, _on_hand),
        Metric("reserved", "Reserved quantity", "units", "snapshot", _scopes, _reserved),
        Metric("operations", "Stock operations", "count", "period", _scopes, _operations),
    ),
)
