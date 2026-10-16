"""Audit domain: validate the safety and bounded size of immutable snapshots."""

import re

ACTION_CODE = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
SENSITIVE_KEY = re.compile(
    r"password|secret|token|credential|cookie|session|authorization|api.?key|"
    r"private.?key|otp|access.?key|refresh.?key",
    flags=re.IGNORECASE,
)


def validate_event_identity(action: str, target_type: str, target_id) -> str:
    if not isinstance(action, str) or not ACTION_CODE.fullmatch(action):
        raise ValueError("Invalid audit action code")
    if not isinstance(target_type, str) or not 1 <= len(target_type) <= 100:
        raise ValueError("Invalid audit target type")
    identifier = str(target_id)
    if not 1 <= len(identifier) <= 128:
        raise ValueError("Invalid audit target identifier")
    return identifier


def sanitize_snapshot(value, depth=0):
    """Reject credential-shaped keys, oversized or non-JSON values."""
    if depth > 5:
        raise ValueError("Audit change snapshot is too deeply nested")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > 500:
            raise ValueError("Audit snapshot string exceeds 500 characters")
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > 50:
            raise ValueError("Audit snapshot list is too large")
        return [sanitize_snapshot(v, depth + 1) for v in value]
    if isinstance(value, dict):
        if len(value) > 30:
            raise ValueError("Audit snapshot dictionary is too large")
        cleaned = {}
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 80 or SENSITIVE_KEY.search(key):
                raise ValueError("Audit snapshot key is invalid or sensitive")
            cleaned[key] = sanitize_snapshot(item, depth + 1)
        return cleaned
    raise ValueError("Audit snapshot must be JSON-safe primitives")
