"""Copyable signed inbound/outbound webhooks with durable Outbox delivery."""

from apps.core.module_registry import Module

MODULE = Module(name="webhooks", requires=("core", "outbox"), priority=31, migration_policy="client")
