"""Portable PrimaryKit module manifest. Discovered automatically from apps/."""

from apps.core.module_registry import Module

MODULE = Module(
    name="notifications",
    requires=("core",),
    optional=(),
    routes=(),
    priority=5,
)
