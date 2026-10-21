"""Standalone private CRM contacts. No Leads/Deals/Kanban coupling."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="contacts",
    requires=("users",),
    optional=("audit",),
    routes=(Route("api/v1/contacts/"),),
    priority=55,
    migration_policy="client",
)
