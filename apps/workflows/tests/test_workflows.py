"""Rules, authorization, optimistic locking and history integration."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, connections, models
from django.test.utils import isolate_apps

from apps.workflows.domain import (
    GuardRejected,
    InvalidTransition,
    StaleTransition,
    TransitionRule,
    WorkflowDefinition,
    WorkflowPermissionDenied,
    decide,
)
from apps.workflows.models import WorkflowStateMixin, WorkflowTransitionHistory
from apps.workflows.services import advance


@pytest.fixture
def definition():
    return WorkflowDefinition(
        states=frozenset({"draft", "approved", "rejected"}),
        initial="draft",
        terminal=frozenset({"approved", "rejected"}),
        transitions=(
            TransitionRule(
                "draft",
                "approve",
                "approved",
                guard=lambda ctx: ctx.aggregate.approvable,
                permission=lambda ctx: ctx.actor == "manager",
            ),
            TransitionRule("draft", "reject", "rejected"),
        ),
    )


def decide_for(definition, **overrides):
    from types import SimpleNamespace

    values = {
        "scope": "order:tenant1",
        "aggregate_id": "82",
        "state": "draft",
        "version": 0,
        "action": "approve",
        "actor": "manager",
        "aggregate": SimpleNamespace(approvable=True),
    }
    values.update(overrides)
    return decide(definition, **values)


def test_deterministic_event_and_immutable_definition(definition):
    a = decide_for(definition)
    b = decide_for(definition, metadata={"reason": "internal"})
    assert a == b
    assert a.version == 1
    assert a.from_state == "draft"
    assert a.to_state == "approved"
    with pytest.raises(FrozenInstanceError):
        a.version = 99
    assert decide_for(definition, version=1).event_id != a.event_id
    assert decide_for(definition, aggregate_id="83").event_id != a.event_id
    assert decide_for(definition, scope="order:tenant2").event_id != a.event_id


@pytest.mark.parametrize(
    "state,action",
    [
        ("approved", "reject"),
        ("rejected", "approve"),
        ("draft", "unknown"),
        ("missing", "approve"),
    ],
)
def test_invalid_transitions_fail_closed(definition, state, action):
    with pytest.raises(InvalidTransition):
        decide_for(definition, state=state, action=action)


def test_permissions_and_guards_are_separate(definition):
    with pytest.raises(WorkflowPermissionDenied):
        decide_for(definition, actor="worker")
    from types import SimpleNamespace

    with pytest.raises(GuardRejected):
        decide_for(definition, aggregate=SimpleNamespace(approvable=False))
    assert decide_for(definition, action="reject", actor="worker").to_state == "rejected"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"states": frozenset()},
        {"states": frozenset({"draft", "Invalid"})},
        {"initial": "unknown"},
        {"terminal": frozenset({"unknown"})},
        {"transitions": (TransitionRule("approved", "undo", "draft"),)},
        {"transitions": (TransitionRule("draft", "noop", "draft"),)},
        {"transitions": (TransitionRule("missing", "approve", "approved"),)},
        {
            "transitions": (
                TransitionRule("draft", "approve", "approved"),
                TransitionRule("draft", "approve", "rejected"),
            )
        },
    ],
)
def test_invalid_workflow_definitions(kwargs):
    values = {
        "states": frozenset({"draft", "approved"}),
        "initial": "draft",
        "terminal": frozenset({"approved"}),
        "transitions": (TransitionRule("draft", "approve", "approved"),),
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        WorkflowDefinition(**values)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scope": ""},
        {"scope": "tenant/injected"},
        {"aggregate_id": "../etc"},
        {"aggregate_id": ""},
        {"version": -1},
        {"version": True},
        {"version": 2**31 - 1},
    ],
)
def test_invalid_identity_and_version_are_rejected(definition, kwargs):
    with pytest.raises(ValueError):
        decide_for(definition, **kwargs)


def test_policy_returns_must_explicitly_allow():
    definition = WorkflowDefinition(
        states=frozenset({"one", "two"}),
        initial="one",
        terminal=frozenset({"two"}),
        transitions=(TransitionRule("one", "go", "two", permission=lambda ctx: 1),),
    )
    with pytest.raises(WorkflowPermissionDenied):
        decide_for(definition, state="one", action="go", aggregate_id="x", actor="manager")


@pytest.fixture
def aggregate_model():
    with isolate_apps("apps.workflows"):

        class TestAggregate(WorkflowStateMixin):
            owner_key = models.CharField(max_length=64)
            approvable = models.BooleanField(default=True)

            class Meta:
                app_label = "workflows"

        with connection.schema_editor() as editor:
            editor.create_model(TestAggregate)
        try:
            yield TestAggregate
        finally:
            with connection.schema_editor() as editor:
                editor.delete_model(TestAggregate)


def _advance(definition, model, pk, **kwargs):
    args = {
        "definition": definition,
        "queryset": model.objects.all(),
        "pk": pk,
        "expected_version": 0,
        "action": "approve",
        "scope": "orders:tenant1",
        "actor": "manager",
        "authorize": lambda actor, obj: actor == "manager" and obj.owner_key == "tenant1",
    }
    args.update(kwargs)
    return advance(**args)


@pytest.mark.django_db(transaction=True)
def test_atomic_transition_persists_state_and_history(aggregate_model, definition):
    obj = aggregate_model.objects.create(owner_key="tenant1", workflow_state="draft")
    event = _advance(definition, aggregate_model, obj.pk, record_history=True)
    obj.refresh_from_db()
    assert (obj.workflow_state, obj.workflow_version) == ("approved", 1)
    rows = list(WorkflowTransitionHistory.objects.all())
    assert len(rows) == 1
    assert rows[0].event_id == event.event_id
    assert (rows[0].scope, rows[0].aggregate_id, rows[0].version) == (
        "orders:tenant1",
        str(obj.pk),
        1,
    )


@pytest.mark.django_db(transaction=True)
def test_repeated_and_wrong_version_rejected(aggregate_model, definition):
    obj = aggregate_model.objects.create(owner_key="tenant1", workflow_state="draft")
    _advance(definition, aggregate_model, obj.pk, record_history=True)
    with pytest.raises(StaleTransition):
        _advance(definition, aggregate_model, obj.pk, record_history=True)
    with pytest.raises(StaleTransition):
        _advance(definition, aggregate_model, obj.pk, expected_version=5, action="reject")
    assert WorkflowTransitionHistory.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_authorization_denies_cross_owner_and_superuser(aggregate_model, definition):
    foreign = aggregate_model.objects.create(owner_key="tenant2", workflow_state="draft")
    for actor in ("manager", "superuser"):
        with pytest.raises(WorkflowPermissionDenied):
            _advance(definition, aggregate_model, foreign.pk, actor=actor, record_history=True)
    foreign.refresh_from_db()
    assert foreign.workflow_version == 0
    assert not WorkflowTransitionHistory.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_guard_failure_does_not_write(aggregate_model, definition):
    obj = aggregate_model.objects.create(
        owner_key="tenant1", workflow_state="draft", approvable=False
    )
    with pytest.raises(GuardRejected):
        _advance(definition, aggregate_model, obj.pk, record_history=True)
    obj.refresh_from_db()
    assert obj.workflow_state == "draft"
    assert obj.workflow_version == 0


@pytest.mark.django_db(transaction=True)
def test_audit_failure_rolls_back_state_and_history(aggregate_model, definition):
    obj = aggregate_model.objects.create(owner_key="tenant1", workflow_state="draft")

    def broken_audit(event):
        raise RuntimeError("audit write failed")

    with pytest.raises(RuntimeError, match="audit write failed"):
        _advance(
            definition,
            aggregate_model,
            obj.pk,
            record_history=True,
            audit_hook=broken_audit,
        )
    obj.refresh_from_db()
    assert obj.workflow_state == "draft"
    assert not WorkflowTransitionHistory.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_history_and_audit_opt_in(aggregate_model, definition):
    obj = aggregate_model.objects.create(owner_key="tenant1", workflow_state="draft")
    events = []
    event = _advance(definition, aggregate_model, obj.pk, audit_hook=events.append)
    assert events == [event]
    assert not WorkflowTransitionHistory.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_authorizer_required(aggregate_model, definition):
    obj = aggregate_model.objects.create(owner_key="tenant1", workflow_state="draft")
    with pytest.raises(TypeError, match="authorize"):
        _advance(definition, aggregate_model, obj.pk, authorize=None)
    obj.refresh_from_db()
    assert obj.workflow_version == 0


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_double_transition(aggregate_model, definition):
    if connection.vendor != "postgresql":
        pytest.skip("Row-lock concurrency requires PostgreSQL")
    obj = aggregate_model.objects.create(owner_key="tenant1", workflow_state="draft")
    barrier = Barrier(2)

    def worker():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            try:
                return _advance(definition, aggregate_model, obj.pk, record_history=True)
            except StaleTransition:
                return "stale"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        results = [f.result(timeout=20) for f in futures]
    assert sum(r == "stale" for r in results) == 1
    assert sum(r != "stale" for r in results) == 1
    assert WorkflowTransitionHistory.objects.count() == 1
