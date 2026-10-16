"""Portable PrimaryKit module manifest. Discovered automatically from apps/."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="inventory",
    requires=("catalog", "organizations"),
    optional=("audit",),
    routes=(Route("api/v1/organizations/<uuid:org_id>/inventory/"),),
    priority=60,
)
