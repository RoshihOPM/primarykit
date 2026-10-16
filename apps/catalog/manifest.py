"""Portable PrimaryKit module manifest. Discovered automatically from apps/."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="catalog",
    requires=("organizations",),
    optional=("audit",),
    routes=(Route("api/v1/organizations/<uuid:org_id>/catalog/"),),
    priority=50,
)
