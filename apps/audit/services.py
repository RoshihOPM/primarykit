"""Explicit audit API; call inside the same transaction as the audited operation."""

import re

from django.core.exceptions import ValidationError

from .models import AuditEvent

_ACTION = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
_SENSITIVE = re.compile(
    r"password|secret|token|credential|cookie|session|authorization|api.?key|"
    r"private.?key|otp|access.?key|refresh.?key",
    flags=re.IGNORECASE,
)


def _validate_snapshot(value, depth=0):
    """Accept bounded, JSON-safe snapshots with no known credential-like fields."""
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
        return [_validate_snapshot(v, depth + 1) for v in value]
    if isinstance(value, dict):
        if len(value) > 30:
            raise ValueError("Audit snapshot dictionary is too large")
        cleaned = {}
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 80 or _SENSITIVE.search(key):
                raise ValueError("Audit snapshot key is invalid or sensitive")
            cleaned[key] = _validate_snapshot(item, depth + 1)
        return cleaned
    raise ValueError("Audit snapshot must be JSON-safe primitives")


def record_event(*, action, target_type, target_id, actor=None, changes=None):
    """Fail closed. A caller modifying business data MUST wrap both writes in atomic()."""
    if not isinstance(action, str) or not _ACTION.fullmatch(action):
        raise ValueError("Invalid audit action code")
    if not isinstance(target_type, str) or not 1 <= len(target_type) <= 100:
        raise ValueError("Invalid audit target type")
    target_id = str(target_id)
    if not 1 <= len(target_id) <= 128:
        raise ValueError("Invalid audit target identifier")
    changes = _validate_snapshot(changes or {})
    if actor is not None and not (actor.is_authenticated and actor.pk):
        raise ValidationError("Actor must be a saved authenticated user or None")
    return AuditEvent.objects.create(
        action=action,
        target_type=target_type,
        target_id=target_id,
        actor=actor,
        changes=changes,
    )
