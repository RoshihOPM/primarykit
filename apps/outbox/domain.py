"""Pure event naming and deterministic delivery identity rules."""

import hashlib
import uuid

from apps.tasks.domain import JOB_CODE, NAMESPACE, validate_job


def validated_envelope(
    *, event_type: str, body: dict, namespace: str, idempotency_key: str | None
) -> dict:
    if not isinstance(event_type, str) or not JOB_CODE.fullmatch(event_type):
        raise ValueError("Invalid outbox event type")
    if not isinstance(namespace, str) or not NAMESPACE.fullmatch(namespace):
        raise ValueError("Invalid outbox namespace")
    if idempotency_key is not None and (
        not isinstance(idempotency_key, str)
        or not 1 <= len(idempotency_key) <= 128
        or not idempotency_key.isascii()
    ):
        raise ValueError("Invalid outbox idempotency key")
    event_id = (
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"{namespace}:{event_type}:{idempotency_key}"))
        if idempotency_key is not None
        else str(uuid.uuid4())
    )
    envelope = {"event_type": event_type, "event_id": event_id, "data": body}
    validate_job(
        namespace=namespace, code="outbox.dispatch", payload=envelope, key=None, attempts=5
    )
    return envelope


def delivery_key(event_type: str, key: str | None) -> str | None:
    if key is None:
        return None
    # Namespace and event type are included in the event-id input. Hash the key
    # so the DB never stores the caller's potentially revealing raw identifier.
    return "outbox:" + hashlib.sha256(f"{event_type}\x00{key}".encode()).hexdigest()
