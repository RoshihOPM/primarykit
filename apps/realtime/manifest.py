"""ASGI WebSocket adapter is opt-in and has no mandatory Redis/broker dependency."""

from apps.core.module_registry import EnvSetting, Module

MODULE = Module(
    name="realtime",
    requires=("users",),
    optional=("chat",),
    priority=86,
    env_settings=(
        EnvSetting("REALTIME_ENABLED", "bool", False),
        EnvSetting("REALTIME_ALLOWED_ORIGINS", "list", ()),
    ),
)
