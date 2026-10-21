"""Optional, portable private conversations. Organizations and Storage are adapters."""

from apps.core.module_registry import EnvSetting, Module, Route

MODULE = Module(
    name="chat",
    requires=("users",),
    optional=("organizations", "storage", "realtime", "audit"),
    routes=(Route("api/v1/"),),
    priority=85,
    migration_policy="client",
    env_settings=(EnvSetting("CHAT_RETENTION_DAYS", "int", 30),),
    throttle_rates=(("chat_read", "120/min"), ("chat_write", "30/min")),
)
