"""Copyable cache utilities; Redis is explicitly opt-in."""

from apps.core.module_registry import Module

MODULE = Module(name="cache", requires=("core",), priority=24)
