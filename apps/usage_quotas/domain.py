"""Pure quota validation. A window is [start, end), independent of billing providers."""

import json
import re
from datetime import datetime

MAX_UNITS = 2**63 - 1
_CODE = re.compile(r"[a-z][a-z0-9_.:-]{0,63}", re.ASCII)
_EVENT_KEY = re.compile(r"[A-Za-z0-9:_-]{1,128}", re.ASCII)


class QuotaRuleError(ValueError):
    """Invalid quota, event, or client policy configuration."""


class QuotaExceeded(QuotaRuleError):
    """The atomic PostgreSQL counter would exceed the allowed quota."""


class QuotaConflict(QuotaRuleError):
    """Policy windows overlap or an event key was reused with different units."""


def validate_units(value: int, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise QuotaRuleError("Units must be an integer.")
    if value < (0 if allow_zero else 1) or value > MAX_UNITS:
        raise QuotaRuleError("Units are outside supported positive bigint range.")
    return value


def validate_code(code: str) -> str:
    if not isinstance(code, str) or not _CODE.fullmatch(code):
        raise QuotaRuleError("Quota code must be a bounded lowercase identifier.")
    return code


def validate_event_key(key: str) -> str:
    if not isinstance(key, str) or not _EVENT_KEY.fullmatch(key):
        raise QuotaRuleError("Invalid usage event key.")
    return key


def validate_window(start: datetime, end: datetime, expires_at: datetime | None) -> None:
    for value in (start, end, expires_at):
        if value is not None and (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise QuotaRuleError("Policy timestamps must be timezone-aware.")
    if start >= end:
        raise QuotaRuleError("Period end must be after period start.")
    if expires_at is not None and expires_at <= start:
        raise QuotaRuleError("Expiration must be after period start.")


def normalize_metadata(metadata: dict | None) -> dict:
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise QuotaRuleError("Policy metadata must be a JSON object.")
    try:
        encoded = json.dumps(metadata, sort_keys=True, allow_nan=False, ensure_ascii=False)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise QuotaRuleError("Policy metadata must contain valid JSON.") from exc
    if len(encoded.encode("utf-8")) > 4096:
        raise QuotaRuleError("Policy metadata exceeds 4 KiB.")
    return json.loads(encoded)


def is_in_window(*, now: datetime, start: datetime, end: datetime,
                 expires_at: datetime | None) -> bool:
    return start <= now < end and (expires_at is None or now < expires_at)
