"""Optional, portable private conversations. Organizations and Storage are adapters."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="chat",
    requires=("users",),
    optional=("organizations", "storage", "realtime", "audit"),
    routes=(Route("api/v1/"),),
    priority=85,
    migration_policy="client",
)
