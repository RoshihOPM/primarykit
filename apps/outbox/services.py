"""Transactional outbox without a second queue or new database schema.

The client registers trusted handler paths for named events. A handler receives
(event_data, *, event_id) and must deduplicate externally observable side effects.
"""

from django.conf import settings
from django.db import connection
from django.utils.module_loading import import_string

from apps.outbox.domain import delivery_key, validated_envelope
from apps.tasks.services import enqueue


def _event_handlers() -> dict[str, str]:
    registry = getattr(settings, "OUTBOX_EVENT_HANDLERS", {})
    if not isinstance(registry, dict):
        raise ValueError("OUTBOX_EVENT_HANDLERS must be a dict")
    return registry


def emit(
    *,
    event_type: str,
    body: dict,
    namespace: str = "default",
    idempotency_key: str | None = None,
):
    """Write the outbox row in the SAME transaction as the business mutation."""
    if not connection.in_atomic_block:
        raise RuntimeError("outbox.emit requires transaction.atomic() around the business write")
    registered = _event_handlers().get(event_type)
    if not isinstance(registered, str) or not registered:
        raise ValueError("Outbox event type has no trusted handler")
    envelope = validated_envelope(
        event_type=event_type, body=body, namespace=namespace, idempotency_key=idempotency_key
    )
    return enqueue(
        code="outbox.dispatch",
        payload=envelope,
        namespace=namespace,
        idempotency_key=delivery_key(event_type, idempotency_key),
    )


def dispatch(envelope: dict) -> None:
    """Called by Tasks worker. Re-check allowlisted event type at execution time."""
    if not isinstance(envelope, dict):
        raise ValueError("Invalid outbox envelope")
    event_type = envelope.get("event_type")
    event_id = envelope.get("event_id")
    body = envelope.get("data")
    if not isinstance(event_id, str) or not isinstance(body, dict):
        raise ValueError("Invalid outbox payload")
    handler_path = _event_handlers().get(event_type)
    if not isinstance(handler_path, str) or not handler_path:
        raise ValueError("Outbox event has no trusted handler")
    handler = import_string(handler_path)
    handler(body, event_id=event_id)
