from apps.core.module_registry import Module

MODULE = Module(name="rate_limit", requires=("core", "cache"), priority=28)
