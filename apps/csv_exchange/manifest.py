"""No mandatory ORM tables or public data exchange endpoints."""

from apps.core.module_registry import Module

MODULE = Module(name="csv_exchange", requires=("core",), priority=28)
