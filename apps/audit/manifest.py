"""Portable PrimaryKit module manifest. Discovered automatically from apps/."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="audit",
    requires=("users",),
    optional=(),
    routes=(
        Route("api/v1/admin/audit/"),
    ),
    priority=30,
)
