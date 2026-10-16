"""Portable Inventory manifest: independent inventory items or optional tenant adapter."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="inventory",
    requires=("users",),
    optional=("catalog", "organizations", "audit"),
    routes=(
        Route("api/v1/inventory/", mode="standalone"),
        Route(
            "api/v1/organizations/<uuid:org_id>/inventory/",
            requires=("catalog", "organizations"),
            mode="tenant",
        ),
    ),
    priority=60,
)
