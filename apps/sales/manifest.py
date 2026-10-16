"""Sales ledger owns its own item snapshots; Orders/Payments are optional."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="sales",
    requires=("users",),
    optional=("orders", "payments", "inventory", "statistics", "audit"),
    routes=(Route("api/v1/sales/"),),
    priority=82,
)
