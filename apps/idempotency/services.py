"""Single-transaction deduplication; use Outbox for all external effects."""

import hashlib
import hmac
import json
import re
from collections.abc import Callable
from typing import Any

from django.db import NotSupportedError, connections, transaction
from django.utils import timezone

from .models import CommandReceipt

_NAME = re.compile(r"^[A-Za-z0-9:_./-]{1,160}$")
_KEY = re.compile(r"^[A-Za-z0-9:_-]{1,128}$")
_MAX_JSON_BYTES = 65536


class IdempotencyConflict(ValueError):
    """A key was reused with another request or an invalid stored receipt."""


def _canonical_bytes(payload: Any) -> bytes:
    try:
        data = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("Payload must be JSON serializable") from exc
    if len(data) > _MAX_JSON_BYTES:
        raise ValueError("Payload exceeds 64 KiB")
    return data


def fingerprint(payload: Any) -> str:
    """Hash canonical bounded JSON; authorization scope is tracked separately."""
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def execute_once(
    *,
    scope: str,
    key: str,
    request: Any,
    operation: Callable[[], Any],
) -> tuple[Any, bool]:
    """Return (result, replayed). The operation must ONLY have DB effects.

    A trusted caller must derive scope from authenticated actor + tenant + action.
    Request/response size is capped. The PostgreSQL unique index and a row lock
    serialize racing callers, and the receipt commits with the domain writes.
    """
    if not isinstance(scope, str) or not _NAME.fullmatch(scope):
        raise ValueError("Invalid idempotency scope")
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError("Invalid idempotency key")
    if not callable(operation):
        raise TypeError("operation must be callable")
    digest = fingerprint(request)
    if connections["default"].vendor != "postgresql":
        raise NotSupportedError("Command idempotency requires PostgreSQL row locks")
    with transaction.atomic():
        receipt, created = CommandReceipt.objects.select_for_update().get_or_create(
            scope=scope, key=key, defaults={"request_digest": digest}
        )
        if not hmac.compare_digest(receipt.request_digest, digest):
            raise IdempotencyConflict("Idempotency key reused with different input")
        if not created:
            if receipt.completed_at is None:
                raise IdempotencyConflict("Stored receipt is incomplete")
            return receipt.response, True
        response = operation()
        _canonical_bytes(response)  # Roll back un-serializable results, including DB writes.
        receipt.response = response
        receipt.completed_at = timezone.now()
        receipt.save(update_fields=["response", "completed_at"])
        return response, False
