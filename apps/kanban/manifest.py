"""Opt-in owner-scoped Kanban boards; CRM is not required."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="kanban",
    requires=("users",),
    optional=("audit",),
    routes=(Route("api/v1/kanban/"),),
    priority=54,
)
