"""PostgreSQL races across optional Orders and Payments boundaries."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.apps import apps
from django.db import close_old_connections, connection, connections
from rest_framework.exceptions import NotFound, ValidationError

from apps.payments.models import PaymentEvent, PaymentIntent
from apps.payments.services import create_intent, reconcile_manual
from apps.users.models import User


def _require_order_module():
    if connection.vendor != "postgresql":
        pytest.skip("Real PostgreSQL transactions and row locks are required")
    if not apps.is_installed("apps.orders"):
        pytest.skip("Orders integration is optional")
    from apps.orders.models import Order
    from apps.orders.services import cancel_order, place_order

    return Order, cancel_order, place_order


def _actors():
    owner = User.objects.create_user(
        email="payment-race-owner@example.test",
        password="payment-race-password-2026",
        email_verified=True,
    )
    root = User.objects.create_user(
        email="payment-race-root@example.test",
        password="payment-root-password-2026",
        email_verified=True,
        is_superuser=True,
        is_staff=True,
    )
    return owner, root


def _order(place_order, owner, key):
    return place_order(
        actor=owner,
        currency="USD",
        lines=[{"sku": "SKU-7", "title": "Book", "quantity": 1, "unit_price_minor": 235}],
        idempotency_key=key,
    )


def _intent(owner, order, key):
    return create_intent(
        actor=owner,
        amount_minor=235,
        currency="USD",
        source_order_id=order.pk,
        idempotency_key=key,
    )


def _settle(root, intent, key):
    return reconcile_manual(
        actor=root,
        payment_id=intent.pk,
        event_key=key,
        outcome="succeeded",
        amount_minor=235,
        currency="USD",
    )


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_settlements_of_one_order_allow_only_one_success():
    _Order, _cancel, place_order = _require_order_module()
    owner, root = _actors()
    order = _order(place_order, owner, "parallel-settlement-order")
    intents = (
        _intent(owner, order, "parallel-settlement-one"),
        _intent(owner, order, "parallel-settlement-two"),
    )
    barrier = Barrier(2)

    def worker(pair):
        number, intent = pair
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            try:
                _settle(root, intent, f"parallel-provider-event-{number}")
                return "succeeded"
            except ValidationError:
                return "rejected"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker, enumerate(intents)))

    assert sorted(results) == ["rejected", "succeeded"]
    statuses = list(
        PaymentIntent.objects.filter(pk__in=[p.pk for p in intents]).values_list(
            "status", flat=True
        )
    )
    assert sorted(statuses) == ["pending", "succeeded"]
    assert PaymentEvent.objects.filter(intent_id__in=[p.pk for p in intents]).count() == 1


@pytest.mark.django_db(transaction=True)
def test_order_cancel_and_payment_settlement_have_no_partial_commit():
    Order, cancel_order, place_order = _require_order_module()
    owner, root = _actors()
    order = _order(place_order, owner, "parallel-cancel-order")
    intent = _intent(owner, order, "parallel-cancel-intent")
    barrier = Barrier(2)

    def worker(action):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            try:
                if action == "cancel":
                    cancel_order(actor=owner, order_id=order.pk)
                else:
                    _settle(root, intent, "parallel-cancel-provider-event")
                return (action, "accepted")
            except (ValidationError, NotFound):
                return (action, "rejected")
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker, ("cancel", "settle")))

    assert sorted(state for _, state in results) == ["accepted", "rejected"]
    order.refresh_from_db()
    intent.refresh_from_db()
    if order.status == Order.Status.CANCELED:
        assert intent.status == PaymentIntent.Status.PENDING
        assert PaymentEvent.objects.filter(intent=intent).count() == 0
    else:
        assert order.status == Order.Status.PLACED
        assert intent.status == PaymentIntent.Status.SUCCEEDED
        assert PaymentEvent.objects.filter(intent=intent, outcome="succeeded").count() == 1
