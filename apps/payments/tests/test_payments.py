"""Payment success must not be forged by owner, even through direct services."""

import pytest
from django.apps import apps
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.payments.models import PaymentEvent, PaymentIntent
from apps.payments.services import create_intent, reconcile_manual
from apps.users.models import User

pytestmark = pytest.mark.django_db


def actor(email, is_root=False):
    user = User.objects.create_user(
        email=email,
        password="secure-payments-password-34567",
        email_verified=True,
        is_superuser=is_root,
        is_staff=is_root,
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return user, api


def request_data():
    return {
        "currency": "USD",
        "amount_minor": 235,
        "idempotency_key": "payment-request-001",
    }


def test_create_is_pending_and_only_superuser_can_reconcile():
    user, api = actor("pay-owner@example.test")
    _, root_api = actor("pay-admin@example.test", is_root=True)
    result = api.post("/api/v1/payments/", {**request_data(), "status": "succeeded"}, format="json")
    assert result.status_code == 201, result.data
    payment_id = result.data["id"]
    assert result.data["status"] == "pending"
    assert api.post("/api/v1/payments/", request_data(), format="json").data["id"] == payment_id
    assert PaymentIntent.objects.count() == 1
    changed = {**request_data(), "amount_minor": 500}
    assert api.post("/api/v1/payments/", changed, format="json").status_code == 400
    endpoint = f"/api/v1/admin/payments/{payment_id}/reconcile/"
    evidence = {
        "event_key": "trusted-proof-001",
        "outcome": "succeeded",
        "amount_minor": 235,
        "currency": "USD",
    }
    assert api.post(endpoint, evidence, format="json").status_code == 403
    with pytest.raises(PermissionDenied):
        reconcile_manual(actor=user, payment_id=payment_id, **evidence)
    mismatched = {**evidence, "amount_minor": 500}
    assert root_api.post(endpoint, mismatched, format="json").status_code == 400
    settled = root_api.post(endpoint, evidence, format="json")
    assert settled.status_code == 200, settled.data
    assert settled.data["status"] == "succeeded"
    assert root_api.post(endpoint, evidence, format="json").status_code == 200
    assert PaymentEvent.objects.count() == 1
    assert api.post(f"/api/v1/payments/{payment_id}/cancel/").status_code == 400


def test_other_user_cannot_read_or_cancel_foreign_intent_even_as_root():
    owner, api = actor("payment-owned@tests.example")
    _, other = actor("payment-stranger@tests.example")
    _, root = actor("payment-superuser@tests.example", is_root=True)
    intent = create_intent(actor=owner, **request_data())
    for attacker in (other, root):
        assert attacker.get("/api/v1/payments/").data["count"] == 0
        assert attacker.get(f"/api/v1/payments/{intent.pk}/").status_code == 404
        assert attacker.post(f"/api/v1/payments/{intent.pk}/cancel/").status_code == 404
    assert api.get(f"/api/v1/payments/{intent.pk}/").status_code == 200


def test_cancel_blocks_settlement_and_prevents_cross_order_payment():
    owner, api = actor("payment-canceled@tests.example")
    _, root = actor("payment-canceled-root@tests.example", is_root=True)
    intent = create_intent(actor=owner, **request_data())
    assert api.post(f"/api/v1/payments/{intent.pk}/cancel/").status_code == 200
    assert api.post(f"/api/v1/payments/{intent.pk}/cancel/").status_code == 400
    assert (
        root.post(
            f"/api/v1/admin/payments/{intent.pk}/reconcile/",
            {
                "event_key": "reconcile-blocked",
                "outcome": "succeeded",
                "amount_minor": 235,
                "currency": "USD",
            },
            format="json",
        ).status_code
        == 400
    )
    if apps.is_installed("apps.orders"):
        from apps.orders.services import place_order

        other, _ = actor("payment-otherorder@tests.example")
        order = place_order(
            actor=other,
            currency="USD",
            idempotency_key="another-order-0001",
            lines=[{"sku": "x", "title": "Item", "quantity": 1, "unit_price_minor": 235}],
        )
        assert (
            api.post(
                "/api/v1/payments/",
                {
                    **request_data(),
                    "idempotency_key": "payment-other-order",
                    "source_order_id": str(order.pk),
                },
                format="json",
            ).status_code
            == 404
        )


def test_reconciliation_event_key_cannot_settle_another_intent():
    """Global settlement event IDs may not be silently replayed for another payment."""
    owner, _ = actor("pay-event-owner@tests.example")
    root, _ = actor("pay-event-root@tests.example", is_root=True)
    first = create_intent(actor=owner, **request_data())
    second = create_intent(
        actor=owner,
        currency="USD",
        amount_minor=235,
        idempotency_key="another-payment-request",
    )
    evidence = {
        "event_key": "provider-event-id-shared",
        "outcome": "succeeded",
        "amount_minor": 235,
        "currency": "USD",
    }
    reconcile_manual(actor=root, payment_id=first.pk, **evidence)
    with pytest.raises(ValidationError, match="Event key conflicts"):
        reconcile_manual(actor=root, payment_id=second.pk, **evidence)

    second.refresh_from_db()
    assert second.status == PaymentIntent.Status.PENDING
    assert PaymentEvent.objects.count() == 1


def test_only_one_successful_payment_per_order():
    """Two pending payment intents may reference one order, but only one can succeed."""
    if not apps.is_installed("apps.orders"):
        pytest.skip("Orders module not installed")
    from apps.orders.services import place_order

    owner, _ = actor("pay-order-owner@tests.example")
    root, _ = actor("pay-order-root@tests.example", is_root=True)
    order = place_order(
        actor=owner,
        currency="USD",
        lines=[{"sku": "book", "title": "Book", "quantity": 1, "unit_price_minor": 235}],
        idempotency_key="payments-order-same-order",
    )
    first = create_intent(
        actor=owner,
        source_order_id=order.pk,
        currency="USD",
        amount_minor=235,
        idempotency_key="pay-order-first-intent",
    )
    second = create_intent(
        actor=owner,
        source_order_id=order.pk,
        currency="USD",
        amount_minor=235,
        idempotency_key="pay-order-second-intent",
    )
    reconcile_manual(
        actor=root,
        payment_id=first.pk,
        event_key="provider-first-order-success",
        outcome="succeeded",
        amount_minor=235,
        currency="USD",
    )
    with pytest.raises(ValidationError, match="already has a successful payment"):
        reconcile_manual(
            actor=root,
            payment_id=second.pk,
            event_key="provider-second-order-success",
            outcome="succeeded",
            amount_minor=235,
            currency="USD",
        )
    second.refresh_from_db()
    assert second.status == PaymentIntent.Status.PENDING
    assert PaymentEvent.objects.count() == 1
