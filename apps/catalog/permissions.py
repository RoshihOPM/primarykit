"""Tenant role policy is enforced by scoped views rather than global Django Groups."""

from rest_framework.permissions import IsAuthenticated


class CatalogAccess(IsAuthenticated):
    """Verified users authenticate through the project's configured DRF auth classes."""
