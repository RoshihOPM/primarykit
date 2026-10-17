"""Transactions, allowlisted handlers, idempotency and at-least-once delivery."""

import pytest
from django.db import transaction
from django.test import override_settings

from apps.outbox.domain import delivery_key, validated_envelope
from apps.outbox.services import emit
from apps.tasks.models import BackgroundJob
from apps.tasks.services import run_next

DELIVERED = []
HANDLERS = {"outbox.dispatch": "apps.outbox.services.dispatch"}
EVENTS = {"lead.created": "apps.outbox.tests.test_outbox.received_event"}


def received_event(body, *, event_id):
    DELIVERED.append((event_id, body))


def test_pure_event_envelope_and_idempotency():
    one = validated_envelope(
        event_type="lead.created", body={"id": 1}, namespace="org:1", idempotency_key="same"
    )
    two = validated_envelope(
        event_type="lead.created", body={"id": 1}, namespace="org:1", idempotency_key="same"
    )
    assert one == two
    assert one["event_id"] != validated_envelope(
        event_type="lead.created", body={"id": 1}, namespace="org:2", idempotency_key="same"
    )["event_id"]
    assert delivery_key("lead.created", "customer@example.test").startswith("outbox:")
    assert "customer" not in delivery_key("lead.created", "customer@example.test")
    with pytest.raises(ValueError):
        validated_envelope(event_type="bad event", body={}, namespace="default", idempotency_key=None)
    with pytest.raises(ValueError):
        validated_envelope(
            event_type="lead.created", body={"data": object()}, namespace="default",
            idempotency_key=None,
        )


@pytest.mark.django_db(transaction=True)
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS, OUTBOX_EVENT_HANDLERS=EVENTS)
def test_outbox_requires_business_transaction_and_rolls_back():
    with pytest.raises(RuntimeError, match="transaction.atomic"):
        emit(event_type="lead.created", body={"id": 1}, idempotency_key="one")
    with pytest.raises(RuntimeError, match="business failed"):
        with transaction.atomic():
            emit(event_type="lead.created", body={"id": 1}, idempotency_key="one")
            raise RuntimeError("business failed")
    assert BackgroundJob.objects.count() == 0


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS, OUTBOX_EVENT_HANDLERS=EVENTS)
def test_durable_dispatch_and_replay_safe_identity():
    DELIVERED.clear()
    with transaction.atomic():
        one = emit(
            event_type="lead.created", body={"id": 21}, namespace="org:1",
            idempotency_key="request-21",
        )
        repeated = emit(
            event_type="lead.created", body={"id": 21}, namespace="org:1",
            idempotency_key="request-21",
        )
    assert repeated.id == one.id
    assert one.code == "outbox.dispatch"
    assert one.payload["event_type"] == "lead.created"
    assert BackgroundJob.objects.count() == 1
    assert run_next()
    assert not run_next()
    one.refresh_from_db()
    assert one.status == BackgroundJob.Status.SUCCEEDED
    assert DELIVERED == [(one.payload["event_id"], {"id": 21})]
    with pytest.raises(ValueError, match="Conflicting"):
        with transaction.atomic():
            emit(
                event_type="lead.created", body={"id": 22}, namespace="org:1",
                idempotency_key="request-21",
            )


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS, OUTBOX_EVENT_HANDLERS=EVENTS)
def test_untrusted_event_fails_before_insert():
    with pytest.raises(ValueError, match="trusted"):
        with transaction.atomic():
            emit(event_type="unknown.event", body={"id": 1})
    assert not BackgroundJob.objects.exists()


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS, OUTBOX_EVENT_HANDLERS={})
def test_handler_disabled_after_persist_retries_instead_of_executing():
    DELIVERED.clear()
    with override_settings(OUTBOX_EVENT_HANDLERS=EVENTS):
        with transaction.atomic():
            job = emit(event_type="lead.created", body={"id": 99})
    assert run_next()
    job.refresh_from_db()
    assert job.status == BackgroundJob.Status.PENDING
    assert job.last_error == "ValueError"
    assert DELIVERED == []
