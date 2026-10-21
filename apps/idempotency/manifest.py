"""Optional PostgreSQL command idempotency; no public HTTP routes."""

from apps.core.module_registry import Module

MODULE = Module(name="idempotency", requires=("core",), priority=24, migration_policy="client")
