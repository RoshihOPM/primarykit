"""Verify real RabbitMQ transport is usable; does not execute business tasks."""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("PRIMARYKIT_INFRA_INTEGRATION") != "1",
    reason="Only run against explicitly provisioned RabbitMQ",
)


def test_real_celery_rabbitmq_connection():
    pytest.importorskip("celery")
    from apps.celery_tasks.celery_app import app

    assert app.conf.broker_url.startswith("amqp://")
    assert app.conf.accept_content == ["json"]
    with app.connection_for_write() as connection:
        connection.ensure_connection(max_retries=5)
        channel = connection.channel()
        try:
            channel.queue_declare(queue="primarykit-ci-smoke", durable=False)
        finally:
            channel.queue_delete(queue="primarykit-ci-smoke")
            channel.close()
