from datetime import UTC, datetime, timedelta

import pytest

from apps.usage_quotas.domain import (
    MAX_UNITS,
    QuotaRuleError,
    is_in_window,
    normalize_metadata,
    validate_code,
    validate_event_key,
    validate_units,
    validate_window,
)


@pytest.mark.parametrize("invalid", [True, 0, -1, 1.5, "4", MAX_UNITS + 1])
def test_units_reject_nonpositive_overflow_and_invalid_types(invalid):
    with pytest.raises(QuotaRuleError):
        validate_units(invalid)


def test_zero_limit_and_valid_upper_bound():
    assert validate_units(0, allow_zero=True) == 0
    assert validate_units(MAX_UNITS) == MAX_UNITS


@pytest.mark.parametrize("invalid", ["", "UPPER", "bad space", "!", "x" * 65, 123])
def test_code_validation(invalid):
    with pytest.raises(QuotaRuleError):
        validate_code(invalid)


@pytest.mark.parametrize("invalid", ["", "bad key", "x" * 129, None])
def test_idempotency_key_validation(invalid):
    with pytest.raises(QuotaRuleError):
        validate_event_key(invalid)


def test_json_snapshot_metadata_bounds_and_serialization():
    assert normalize_metadata({"tier": "example", "revision": 1}) == {
        "revision": 1, "tier": "example"
    }
    for invalid in ({"a": float("nan")}, {"x": object()}, {"x": "y" * 5000}, []):
        with pytest.raises(QuotaRuleError):
            normalize_metadata(invalid)


def test_start_inclusive_end_and_expiration_exclusive():
    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = start + timedelta(days=30)
    expires = start + timedelta(days=2)
    validate_window(start, end, expires)
    assert is_in_window(now=start, start=start, end=end, expires_at=expires)
    assert not is_in_window(now=expires, start=start, end=end, expires_at=expires)
    assert not is_in_window(now=end, start=start, end=end, expires_at=None)
    assert not is_in_window(now=start - timedelta(microseconds=1), start=start,
                            end=end, expires_at=None)


def test_invalid_timestamps_fail_closed():
    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = start + timedelta(days=1)
    for args in ((end, start, None), (start, start, None), (start.replace(tzinfo=None),
                 end, None), (start, end, start), (start, end, start.replace(tzinfo=None))):
        with pytest.raises(QuotaRuleError):
            validate_window(*args)
