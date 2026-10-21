"""Client-owned state transitions; no public endpoints or required business apps."""

from apps.core.module_registry import Module

MODULE = Module(name="workflows", requires=("core",), optional=("audit", "outbox"), priority=28, migration_policy="client")
