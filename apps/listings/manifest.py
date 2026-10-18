"""Portable, opt-in listings API. No dependency on Catalog or Inventory."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="listings",
    requires=("users",),
    optional=("audit", "search", "storage", "organizations"),
    routes=(Route("api/v1/listings/"),),
    priority=55,
)
