"""Copy-ready read-only metrics module with optional provider integrations."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="statistics",
    requires=("users",),
    optional=("catalog", "inventory", "storage", "organizations", "audit"),
    routes=(
        Route("api/v1/statistics/"),
        Route(
            "api/v1/organizations/<uuid:org_id>/statistics/",
            requires=("organizations",),
        ),
        Route("api/v1/admin/statistics/", urlconf="apps.statistics.system_urls"),
    ),
    priority=80,
)
