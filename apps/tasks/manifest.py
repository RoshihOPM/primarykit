"""Portable DB-backed internal background jobs, no API or required broker."""

from apps.core.module_registry import Module

MODULE = Module(
    name="tasks",
    requires=("core",),
    priority=25,
    migration_policy="client",
)
