# ruff: noqa: F401
"""Stable catalog models facade exposing the project-pinned schema mode."""

from django.conf import settings

if settings.CATALOG_MODE == "tenant":
    from .tenant_models import (
        AttributeDefinition,
        CatalogItem,
        Category,
    )
elif settings.CATALOG_MODE == "standalone":
    from .standalone_models import (
        AttributeDefinition,
        CatalogItem,
        Category,
    )
else:
    raise ValueError("Invalid CATALOG_MODE; use tenant or standalone")
