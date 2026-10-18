"""Optional favorites and saved searches for published seller listings."""

from apps.core.module_registry import Module, Route

MODULE = Module(
    name="favorites",
    requires=("listings",),
    routes=(Route("api/v1/"),),
    priority=57,
)
