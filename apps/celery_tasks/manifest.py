"""Optional Celery worker adapter; no dependency on DB-backed Tasks or cache."""

from apps.core.module_registry import Module

MODULE = Module(name="celery_tasks", requires=("core",), priority=26)
