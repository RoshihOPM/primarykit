"""Audit application service: validate event data, persist inside caller transaction."""

from django.core.exceptions import ValidationError

from .domain import sanitize_snapshot, validate_event_identity
from .models import AuditEvent


def record_event(*, action, target_type, target_id, actor=None, changes=None):
    """Fail closed. The caller wraps its business mutation and this write in atomic()."""
    target_id = validate_event_identity(action, target_type, target_id)
    changes = sanitize_snapshot(changes or {})
    if actor is not None and not (actor.is_authenticated and actor.pk):
        raise ValidationError("Actor must be a saved authenticated user or None")
    return AuditEvent.objects.create(
        action=action,
        target_type=target_type,
        target_id=target_id,
        actor=actor,
        changes=changes,
    )
