"""Opt-in owner-scoped Kanban boards; CRM is not required."""

from apps.core.module_registry import Module

MODULE = Module(name="kanban", requires=("users",), optional=("audit",), priority=54)
