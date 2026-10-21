"""Portable PrimaryKit module manifest. Discovered automatically from apps/."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="users",
    requires=("core", "notifications"),
    optional=("audit",),
    routes=(Route("api/v1/"),),
    priority=10,
    migration_policy="client",
)
