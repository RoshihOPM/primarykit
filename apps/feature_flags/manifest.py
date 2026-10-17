"""Optional local flags. No database, route, Redis or kit runtime dependency."""

from apps.core.module_registry import Module

MODULE = Module(name="feature_flags", requires=("core",), priority=26)
