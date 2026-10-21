"""Independent machine credentials with optional audit."""

from apps.core.module_registry import Module

MODULE = Module(
    name="api_keys",
    requires=("users",),
    optional=("audit",),
    priority=35,
    migration_policy="client",
)
