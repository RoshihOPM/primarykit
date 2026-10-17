"""No public quota-granting endpoint: clients opt into business rules explicitly."""

from apps.core.module_registry import Module

MODULE = Module(
    name="usage_quotas",
    requires=("users",),
    optional=("organizations", "statistics"),
    priority=77,
)
