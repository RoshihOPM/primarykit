"""No index ownership, migrations or public endpoint."""

from apps.core.module_registry import Module

MODULE = Module(name="search", requires=("core",), priority=27)
