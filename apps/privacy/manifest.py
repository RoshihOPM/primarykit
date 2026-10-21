"""Privacy requires an audited durable queue; no public HTTP endpoints."""

from apps.core.module_registry import Module

MODULE = Module(
    name="privacy",
    requires=("core", "audit", "tasks"),
    priority=55,
    migration_policy="client",
)
