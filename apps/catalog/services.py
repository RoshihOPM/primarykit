"""Normalize and validate category-specific attribute values."""

from decimal import Decimal, InvalidOperation

from rest_framework.exceptions import ValidationError

from .models import AttributeDefinition


def validate_attributes(category, supplied):
    if not isinstance(supplied, dict):
        raise ValidationError({"attributes": "Expected an object."})
    definitions = list(AttributeDefinition.objects.filter(category=category))
    allowed = {definition.code: definition for definition in definitions}
    if set(supplied) - set(allowed):
        raise ValidationError({"attributes": "Unknown attribute code for this category."})
    required = {d.code for d in definitions if d.required}
    if required - set(supplied):
        raise ValidationError({"attributes": "Required category attributes are missing."})
    normalized = {}
    for code, value in supplied.items():
        kind = allowed[code].data_type
        if kind == AttributeDefinition.DataType.TEXT:
            if not isinstance(value, str) or not value.strip() or len(value) > 500:
                raise ValidationError({"attributes": f"{code} must be nonempty text (max 500)."})
            normalized[code] = value.strip()
        elif kind == AttributeDefinition.DataType.INTEGER:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValidationError({"attributes": f"{code} must be an integer."})
            normalized[code] = value
        elif kind == AttributeDefinition.DataType.BOOLEAN:
            if not isinstance(value, bool):
                raise ValidationError({"attributes": f"{code} must be a boolean."})
            normalized[code] = value
        elif kind == AttributeDefinition.DataType.DECIMAL:
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise ValidationError({"attributes": f"{code} must be a decimal."})
            try:
                parsed = Decimal(str(value))
            except InvalidOperation as exc:
                raise ValidationError({"attributes": f"{code} must be a decimal."}) from exc
            if not parsed.is_finite() or len(parsed.as_tuple().digits) > 24 or abs(parsed.as_tuple().exponent) > 8:
                raise ValidationError({"attributes": f"{code} is outside supported precision."})
            normalized[code] = str(parsed)
        else:
            raise ValidationError({"attributes": "Unknown category data type."})
    return normalized
