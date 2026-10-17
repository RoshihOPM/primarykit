"""Opt-in trusted outbound HTTPS transport without external package dependencies."""

from apps.core.module_registry import Module

MODULE = Module(name="http_integrations", requires=("core",), priority=23)
