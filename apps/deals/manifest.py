"""Standalone Deals and monetary snapshots; no payments or Leads coupling."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="deals",
    requires=("users",),
    optional=("audit",),
    routes=(Route("api/v1/deals/"),),
    priority=55,
    migration_policy="client",
)
