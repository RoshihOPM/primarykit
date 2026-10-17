"""Portable transactional event outbox implemented via the existing Tasks ledger."""

from apps.core.module_registry import Module

MODULE = Module(name="outbox", requires=("core", "tasks"), priority=27)
