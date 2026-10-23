"""PostgreSQL-only checks for real order idempotency row locks."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, connections
from rest_framework.exceptions import ValidationError

from apps.orders.models import Order, OrderItem
from apps.orders.services import place_order
from apps.users.models import User


def _owner():
    return User.objects.create_user(
        email="order-race-owner@example.test",
        password="strong-order-race-password-2026",
        email_verified=True,
    )


def _lines(price):
    return [{"sku": "RACE-1", "title": "Concurrent item", "quantity": 2, "unit_price_minor": price}]


@pytest.mark.django_db(transaction=True)
def test_simultaneous_order_replays_return_single_snapshot():
    if connection.vendor != "postgresql":
        pytest.skip("Real PostgreSQL row locks are required")

    owner = _owner()
    barrier = Barrier(2)

    def worker(_number):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            result = place_order(
                actor=owner,
                currency="USD",
                lines=_lines(125),
                idempotency_key="same-concurrent-order",
            )
            return result.pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(worker, (1, 2)))

    assert ids[0] == ids[1]
    assert Order.objects.filter(owner=owner, idempotency_key="same-concurrent-order").count() == 1
    assert OrderItem.objects.filter(order_id=ids[0]).count() == 1
    order = Order.objects.get(pk=ids[0])
    assert order.status == Order.Status.PLACED
    assert order.total_minor == 250


@pytest.mark.django_db(transaction=True)
def test_simultaneous_reuse_with_different_payload_rejects_one_writer():
    if connection.vendor != "postgresql":
        pytest.skip("Real PostgreSQL row locks are required")

    owner = _owner()
    barrier = Barrier(2)

    def worker(price):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            try:
                order = place_order(
                    actor=owner,
                    currency="USD",
                    lines=_lines(price),
                    idempotency_key="conflicting-concurrent-order",
                )
                return ("accepted", order.pk, price)
            except ValidationError:
                return ("rejected", None, price)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker, (125, 999)))

    assert sorted(result[0] for result in results) == ["accepted", "rejected"]
    winner = next(result for result in results if result[0] == "accepted")
    order = Order.objects.get(owner=owner, idempotency_key="conflicting-concurrent-order")
    assert order.pk == winner[1]
    assert order.total_minor == 2 * winner[2]
    assert list(OrderItem.objects.filter(order=order).values_list("unit_price_minor", flat=True)) == [
        winner[2]
    ]
