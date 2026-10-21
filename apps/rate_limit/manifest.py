from apps.core.module_registry import EnvSetting, Module

MODULE = Module(name="rate_limit", requires=("core", "cache"), priority=28, env_settings=(EnvSetting("RATE_LIMIT_SHARED_ACCOUNT_THROTTLE_ENABLED", "bool", False),))
