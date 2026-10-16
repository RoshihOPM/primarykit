"""Pure Catalog domain rules. No Django, DRF, ORM or transport dependencies."""

from decimal import Decimal, InvalidOperation


class CatalogRuleViolation(ValueError):
    """A category attribute violates its declared business constraints."""


def normalize_attributes(definitions, supplied):
    """Validate attributes against simple specs with code/data_type/required fields.

    Callers resolve persisted definitions before entering the domain.
    """
    if not isinstance(supplied, dict):
        raise CatalogRuleViolation("Expected an object.")
    allowed = {definition.code: definition for definition in definitions}
    if set(supplied) - set(allowed):
        raise CatalogRuleViolation("Unknown attribute code for this category.")
    required = {definition.code for definition in definitions if definition.required}
    if required - set(supplied):
        raise CatalogRuleViolation("Required category attributes are missing.")
    normalized = {}
    for code, value in supplied.items():
        kind = allowed[code].data_type
        if kind == "text":
            if not isinstance(value, str) or not value.strip() or len(value) > 500:
                raise CatalogRuleViolation(f"{code} must be nonempty text (max 500).")
            normalized[code] = value.strip()
        elif kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise CatalogRuleViolation(f"{code} must be an integer.")
            normalized[code] = value
        elif kind == "boolean":
            if not isinstance(value, bool):
                raise CatalogRuleViolation(f"{code} must be a boolean.")
            normalized[code] = value
        elif kind == "decimal":
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise CatalogRuleViolation(f"{code} must be a decimal.")
            try:
                parsed = Decimal(str(value))
            except InvalidOperation as exc:
                raise CatalogRuleViolation(f"{code} must be a decimal.") from exc
            if (
                not parsed.is_finite()
                or len(parsed.as_tuple().digits) > 24
                or abs(parsed.as_tuple().exponent) > 8
            ):
                raise CatalogRuleViolation(f"{code} is outside supported precision.")
            normalized[code] = str(parsed)
        else:
            raise CatalogRuleViolation("Unknown category data type.")
    return normalized


def normalize_sku(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise CatalogRuleViolation("SKU cannot be empty.")
    return normalized


def belongs_to_tenant(*, parent_organization_id, child_organization_id) -> bool:
    return parent_organization_id == child_organization_id
