"""Pure domain validation and publication lifecycle for classifieds."""

import json
import re

VALID_CURRENCIES = re.compile(r"^[A-Z]{3}$")
TRANSITIONS = {
    ("draft", "submit"): "pending",
    ("rejected", "submit"): "pending",
    ("pending", "approve"): "published",
    ("pending", "reject"): "rejected",
    ("draft", "archive"): "archived",
    ("rejected", "archive"): "archived",
    ("published", "archive"): "archived",
    ("published", "mark_sold"): "sold",
}


class ListingRuleError(ValueError):
    """A draft field or lifecycle transition violates a classifieds invariant."""


def next_status(current: str, action: str) -> str:
    try:
        return TRANSITIONS[(current, action)]
    except KeyError as exc:
        raise ListingRuleError("This listing transition is not permitted.") from exc


def normalize_fields(fields: dict) -> dict:
    """Validate the full listing snapshot without Django, ORM or external services."""
    if not isinstance(fields, dict):
        raise ListingRuleError("Listing fields must be an object.")
    title = fields.get("title")
    description = fields.get("description", "")
    location = fields.get("location_label", "")
    price = fields.get("price_minor")
    currency = fields.get("currency")
    attrs = fields.get("attributes", {})
    if not isinstance(title, str) or not 3 <= len(title.strip()) <= 200:
        raise ListingRuleError("Title must contain 3-200 characters.")
    if not isinstance(description, str) or len(description) > 10000:
        raise ListingRuleError("Description is limited to 10,000 characters.")
    if not isinstance(location, str) or len(location.strip()) > 120:
        raise ListingRuleError("Location label is limited to 120 characters.")
    if type(price) is not int or not 0 <= price <= 10**15:
        raise ListingRuleError("Price in minor currency units must be 0-10^15.")
    if not isinstance(currency, str) or not VALID_CURRENCIES.fullmatch(currency):
        raise ListingRuleError("Currency must be a three-letter uppercase code.")
    if not isinstance(attrs, dict) or len(attrs) > 24:
        raise ListingRuleError("Attributes must be an object with at most 24 entries.")
    if any(not isinstance(k, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", k) for k in attrs):
        raise ListingRuleError("Invalid attribute name.")
    try:
        encoded = json.dumps(attrs, allow_nan=False, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ListingRuleError("Attributes must be JSON serializable.") from exc
    if len(encoded.encode("utf-8")) > 8192:
        raise ListingRuleError("Attributes exceed 8 KiB.")
    if any(isinstance(v, (list, dict)) for v in attrs.values()):
        raise ListingRuleError("Nested attribute values are unsupported.")
    return {
        "title": title.strip(),
        "description": description,
        "location_label": location.strip(),
        "price_minor": price,
        "currency": currency,
        "attributes": attrs,
    }
