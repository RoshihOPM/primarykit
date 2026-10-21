"""Portable PrimaryKit module manifest. Discovered automatically from apps/."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="organizations",
    requires=("users",),
    optional=("audit",),
    routes=(Route("api/v1/"),),
    priority=70,
    migration_policy="client",
)
