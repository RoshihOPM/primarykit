"""ASGI WebSocket adapter is opt-in and has no mandatory Redis/broker dependency."""

from apps.core.module_registry import Module

MODULE = Module(
    name="realtime",
    requires=("users",),
    optional=("chat",),
    priority=86,
)
