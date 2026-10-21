"""Portable PrimaryKit module manifest. Discovered automatically from apps/."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="storage",
    requires=("users", "core"),
    optional=("organizations", "audit"),
    routes=(
        Route("api/v1/"),
        Route("api/v1/organizations/<uuid:org_id>/", requires=("organizations",)),
    ),
    priority=40,
    migration_policy="client",
)
