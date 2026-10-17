"""Transactional adapter for client-owned aggregate state.

No generic public endpoint: the caller supplies an authorization policy and
an appropriately scoped queryset. All callbacks run inside the transaction.
Use Outbox for external effects, not network requests in audit_hook.
"""

from collections.abc import Callable, Mapping
from typing import Any

from django.db import transaction
from django.db.models import QuerySet

from .domain import (
    StaleTransition,
    TransitionEvent,
    WorkflowDefinition,
    WorkflowPermissionDenied,
    decide,
)
from .models import WorkflowTransitionHistory

Authorizer = Callable[[Any, Any], bool]
AuditHook = Callable[[TransitionEvent], None]


def advance(
    *,
    definition: WorkflowDefinition,
    queryset: QuerySet,
    pk: Any,
    expected_version: int,
    action: str,
    scope: str,
    actor: Any,
    authorize: Authorizer,
    state_field: str = "workflow_state",
    version_field: str = "workflow_version",
    metadata: Mapping[str, Any] | None = None,
    record_history: bool = False,
    audit_hook: AuditHook | None = None,
) -> TransitionEvent:
    """Atomically move a client-owned row using row locks and compare-and-swap.

    The client must scope queryset to the authorized aggregate, and authorize
    must repeat the ownership check inside the transaction. Expected version is
    required even if the destination state matches a previous state.
    """
    if not isinstance(queryset, QuerySet):
        raise TypeError("queryset must be a Django QuerySet")
    if not callable(authorize):
        raise TypeError("authorize(actor, aggregate) is required")
    if audit_hook is not None and not callable(audit_hook):
        raise TypeError("audit_hook must be callable")
    if type(expected_version) is not int or expected_version < 0:
        raise ValueError("expected_version must be a nonnegative integer")
    if state_field == version_field:
        raise ValueError("state and version fields must be different")
    for field_name in (state_field, version_field):
        field = queryset.model._meta.get_field(field_name)
        if not field.concrete or field.is_relation:
            raise ValueError("Workflow state and version fields must be concrete columns")
    using = queryset.db
    with transaction.atomic(using=using):
        aggregate = queryset.select_for_update().get(pk=pk)
        if authorize(actor, aggregate) is not True:
            raise WorkflowPermissionDenied("Aggregate access denied")
        state = getattr(aggregate, state_field)
        current_version = getattr(aggregate, version_field)
        if current_version != expected_version:
            raise StaleTransition("Aggregate version has changed")
        event = decide(
            definition,
            scope=scope,
            aggregate_id=str(aggregate.pk),
            state=state,
            version=current_version,
            action=action,
            actor=actor,
            aggregate=aggregate,
            metadata=metadata,
        )
        changed = queryset.filter(
            pk=aggregate.pk,
            **{state_field: state, version_field: current_version},
        ).update(**{state_field: event.to_state, version_field: event.version})
        if changed != 1:
            raise StaleTransition("Concurrent workflow update")
        if record_history:
            WorkflowTransitionHistory.objects.using(using).create(
                event_id=event.event_id,
                scope=event.scope,
                aggregate_id=event.aggregate_id,
                version=event.version,
                action=event.action,
                from_state=event.from_state,
                to_state=event.to_state,
            )
        if audit_hook is not None:
            audit_hook(event)
        return event
