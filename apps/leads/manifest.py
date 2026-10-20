"""Portable Leads without hard Kanban or Organizations dependencies."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="leads",
    requires=("users",),
    optional=("audit", "organizations"),
    routes=(Route("api/v1/leads/"),),
    priority=55,
)
