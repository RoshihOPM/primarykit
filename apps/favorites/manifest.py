"""Optional favorites and saved searches for published seller listings."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="favorites",
    requires=("listings",),
    routes=(Route("api/v1/"),),
    priority=57,
    migration_policy="client",
    throttle_rates=(("favorites_read", "120/min"), ("favorites_write", "60/min")),
)
