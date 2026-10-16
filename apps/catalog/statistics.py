"""Catalog-owned metrics: accessible only inside the active schema's scope."""

from django.conf import settings

from apps.statistics.domain import Metric, Provider

from .models import CatalogItem, Category


def _scope(context):
    if settings.CATALOG_MODE == "standalone":
        return {"owner": context.actor}
    return {"organization": context.organization}


def _items(context):
    return CatalogItem.objects.filter(**_scope(context)).count()


def _active_items(context):
    return CatalogItem.objects.filter(**_scope(context), is_active=True).count()


def _categories(context):
    return Category.objects.filter(**_scope(context)).count()


def _new_items(context):
    return CatalogItem.objects.filter(
        **_scope(context), created_at__gte=context.since, created_at__lt=context.until
    ).count()


_scopes = ("personal",) if settings.CATALOG_MODE == "standalone" else ("tenant",)
PROVIDER = Provider(
    code="catalog",
    metrics=(
        Metric("items", "Catalog items", "count", "snapshot", _scopes, _items),
        Metric("active_items", "Active catalog items", "count", "snapshot", _scopes, _active_items),
        Metric("categories", "Categories", "count", "snapshot", _scopes, _categories),
        Metric("new_items", "New catalog items", "count", "period", _scopes, _new_items),
    ),
)
