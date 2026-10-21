"""Provider-neutral payment intents; no required Orders/Sales dependency."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="payments",
    requires=("users",),
    optional=("orders", "sales", "statistics", "audit"),
    routes=(
        Route("api/v1/payments/"),
        Route("api/v1/admin/payments/", urlconf="apps.payments.admin_urls"),
    ),
    priority=83,
    migration_policy="client",
)
