"""Pure validation and retry rules for internal background commands."""

import json
import re
from datetime import datetime

JOB_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")
NAMESPACE = re.compile(r"^[a-zA-Z0-9_.:-]{1,80}$")
MAX_PAYLOAD_BYTES = 64 * 1024


def validate_job(*, namespace: str, code: str, payload: dict, key: str | None, attempts: int):
    if not isinstance(namespace, str) or not NAMESPACE.fullmatch(namespace):
        raise ValueError("Invalid job namespace")
    if not isinstance(code, str) or not JOB_CODE.fullmatch(code):
        raise ValueError("Invalid job code")
    if type(payload) is not dict:
        raise ValueError("Job payload must be a JSON object")
    try:
        encoded = json.dumps(payload, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Job payload must be valid JSON") from exc
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("Job payload is too large")
    if key is not None and (
        not isinstance(key, str) or not 1 <= len(key) <= 128 or not key.isascii()
    ):
        raise ValueError("Invalid idempotency key")
    if type(attempts) is not int or not 1 <= attempts <= 10:
        raise ValueError("max_attempts must be an integer from 1 to 10")
    return json.loads(encoded)


def require_aware_datetime(value: datetime):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("run_after must be a timezone-aware datetime")


def retry_seconds(attempt: int) -> int:
    """Bounded exponential delay; attempt numbers start at one."""
    return min(3600, 2 ** min(max(attempt, 1), 12))
