"""Celery adapter is safe without Celery/RabbitMQ/Redis installed."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction

from apps.celery_tasks.config import validate_broker
from apps.celery_tasks.dispatch import send_after_commit


@pytest.mark.parametrize(
    "broker",
    ["", "http://localhost", "amqp:///", "file:///etc/passwd", "redis://", "amqp://rabbit:0"],
)
def test_rejects_missing_or_invalid_broker(broker):
    with pytest.raises(ImproperlyConfigured):
        validate_broker(broker=broker)


def test_rabbit_broker_and_optional_redis_results():
    validate_broker(broker="amqp://user:pass@rabbitmq:5672//")
    validate_broker(
        broker="amqps://worker:pass@rabbitmq:5671//",
        backend="rediss://results:6380/1",
    )
    with pytest.raises(ImproperlyConfigured):
        validate_broker(broker="amqp://rabbitmq:5672//", backend="http://bad")


def test_sender_uses_on_commit_not_a_private_runtime_service(monkeypatch):
    callbacks = []

    def capture(function):
        callbacks.append(function)

    monkeypatch.setattr(transaction, "on_commit", capture)

    class FakeTask:
        def __init__(self):
            self.called = []

        def apply_async(self, *, args, kwargs):
            self.called.append((args, kwargs))

    task = FakeTask()
    send_after_commit(task, 12, active=True)
    assert task.called == []
    assert len(callbacks) == 1
    callbacks.pop()()
    assert task.called == [((12,), {"active": True})]
