"""Opt-in glue; base Deals and Kanban remain standalone and independent."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="crm_pipeline",
    requires=("deals", "kanban"),
    routes=(Route("api/v1/crm/pipeline/"),),
    priority=85,
    migration_policy="client",
)
