"""Catalog application service: resolve persisted definitions then run domain rules."""

from rest_framework.exceptions import ValidationError

from .domain import CatalogRuleViolation, normalize_attributes
from .models import AttributeDefinition


def validate_attributes(category, supplied):
    definitions = list(AttributeDefinition.objects.filter(category=category))
    try:
        return normalize_attributes(definitions, supplied)
    except CatalogRuleViolation as exc:
        raise ValidationError({"attributes": str(exc)}) from exc
