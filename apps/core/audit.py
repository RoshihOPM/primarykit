"""Dependency-light integration point for optionally copied audit app."""

from django.apps import apps


def record_audit_event(*, action, target_type, target_id, actor=None, changes=None):
    """No-op when audit app isn't installed; failures propagate when it is."""
    if not apps.is_installed("apps.audit"):
        return None
    from apps.audit.services import record_event

    return record_event(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        changes=changes,
    )
