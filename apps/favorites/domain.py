"""Pure, bounded saved-search filter rules compatible with Listings v1."""

import re

MAX_SAVED_SEARCHES = 20
MAX_PRICE_MINOR = 10**15
TEXT_LIMITS = {"q": 80, "location": 120, "category": 80}
PRICE_FILTERS = ("min_price", "max_price")
FILTER_KEYS = frozenset(TEXT_LIMITS) | frozenset(PRICE_FILTERS)


def normalize_filters(value: dict) -> dict:
    if not isinstance(value, dict) or not value:
        raise ValueError("Filters must be a nonempty object.")
    unknown = set(value) - FILTER_KEYS
    if unknown:
        raise ValueError("Unsupported search filters.")
    result = {}
    for key in TEXT_LIMITS:
        if key not in value:
            continue
        raw = value[key]
        if not isinstance(raw, str):
            raise ValueError(f"{key} must be text.")
        normalized = raw.strip()
        if not normalized or len(normalized) > TEXT_LIMITS[key]:
            raise ValueError(f"{key} has an invalid length.")
        if key == "category" and not re.fullmatch(r"[a-zA-Z0-9_-]+", normalized):
            raise ValueError("Invalid category slug.")
        result[key] = normalized
    for key in PRICE_FILTERS:
        if key not in value:
            continue
        raw = value[key]
        if type(raw) is not int or not 0 <= raw <= MAX_PRICE_MINOR:
            raise ValueError(f"{key} must be a nonnegative integer in minor units.")
        result[key] = raw
    if (
        "min_price" in result
        and "max_price" in result
        and result["min_price"] > result["max_price"]
    ):
        raise ValueError("min_price cannot exceed max_price.")
    return result
