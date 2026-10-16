# ruff: noqa: F401
"""Stable catalog views facade exposing the project-pinned schema mode."""

from django.conf import settings

if settings.CATALOG_MODE == "tenant":
    from .tenant_views import (
        AttributeDefinitionViewSet,
        CatalogItemViewSet,
        CategoryViewSet,
    )
elif settings.CATALOG_MODE == "standalone":
    from .standalone_views import (
        AttributeDefinitionViewSet,
        CatalogItemViewSet,
        CategoryViewSet,
    )
else:
    raise ValueError("Invalid CATALOG_MODE; use tenant or standalone")
