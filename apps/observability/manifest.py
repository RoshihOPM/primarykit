"""Optional zero-external-service request tracing and JSON logging."""

from apps.core.module_registry import Module

MODULE = Module(name="observability", requires=("core",), priority=29)
