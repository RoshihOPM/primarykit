"""Portable, opt-in listings API. No dependency on Catalog or Inventory."""

from apps.core.module_registry import EnvSetting, Module, Route

MODULE = Module(
    name="listings",
    requires=("users",),
    optional=("audit", "search", "storage", "organizations"),
    routes=(Route("api/v1/listings/"),),
    priority=55,
    migration_policy="client",
    env_settings=(EnvSetting("LISTINGS_MEDIA_ENABLED", "bool", False),),
)
