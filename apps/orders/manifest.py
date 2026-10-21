"""Standalone order snapshots; optional Catalog, Sales and Payments integration."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="orders",
    requires=("users",),
    optional=("catalog", "inventory", "sales", "payments", "statistics", "audit"),
    routes=(Route("api/v1/orders/"),),
    priority=81,
    migration_policy="client",
)
