# ruff: noqa: F401
"""Stable catalog serializers facade exposing the project-pinned schema mode."""

from django.conf import settings

if settings.CATALOG_MODE == "tenant":
    from .tenant_serializers import (
        AttributeDefinitionSerializer,
        CatalogItemSerializer,
        CategorySerializer,
    )
elif settings.CATALOG_MODE == "standalone":
    from .standalone_serializers import (
        AttributeDefinitionSerializer,
        CatalogItemSerializer,
        CategorySerializer,
    )
else:
    raise ValueError("Invalid CATALOG_MODE; use tenant or standalone")
