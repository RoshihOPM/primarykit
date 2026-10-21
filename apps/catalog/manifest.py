"""Portable Catalog manifest with pinned standalone / organization schemas."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="catalog",
    requires=("users",),
    optional=("organizations", "audit"),
    routes=(
        Route("api/v1/catalog/", mode="standalone"),
        Route(
            "api/v1/organizations/<uuid:org_id>/catalog/",
            requires=("organizations",),
            mode="tenant",
        ),
    ),
    priority=50,
    migration_policy="client",
)
