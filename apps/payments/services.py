"""Payment intent lifecycle and privileged manual settlement verification.

Production gateways must call a separate signed webhook adapter; this service
never trusts a client-supplied success status.
"""

import hashlib
import json
import uuid

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.core.audit import record_audit_event

from .domain import PaymentRuleViolation, can_cancel, can_reconcile, validate_money
from .models import PaymentEvent, PaymentIntent


def _owner(actor):
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise NotFound()
    user = get_user_model().objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if user is None:
        raise NotFound()
    return user


def _source_order(*, owner, source_order_id, currency, amount_minor):
    if source_order_id is None:
        return None
    if not apps.is_installed("apps.orders"):
        raise ValidationError({"source_order_id": "Orders module is not installed."})
    try:
        source_order_id = uuid.UUID(str(source_order_id))
    except (ValueError, TypeError) as exc:
        raise ValidationError({"source_order_id": "Invalid order identifier."}) from exc
    from apps.orders.models import Order

    order = (
        Order.objects.select_for_update()
        .filter(pk=source_order_id, owner=owner, status="placed")
        .first()
    )
    if order is None:
        raise NotFound()
    if order.currency != currency or order.total_minor != amount_minor:
        raise ValidationError({"source_order_id": "Payment amount/currency differs from order."})
    return order.pk


@transaction.atomic
def create_intent(*, actor, amount_minor, currency, idempotency_key, source_order_id=None):
    try:
        validate_money(currency, amount_minor)
    except PaymentRuleViolation as exc:
        raise ValidationError({"amount_minor": str(exc)}) from exc
    reference = None if source_order_id is None else str(source_order_id)
    fingerprint = hashlib.sha256(
        json.dumps(
            {"amount_minor": amount_minor, "currency": currency, "source_order_id": reference},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    owner = _owner(actor)
    previous = PaymentIntent.objects.filter(owner=owner, idempotency_key=idempotency_key).first()
    if previous:
        if previous.fingerprint != fingerprint:
            raise ValidationError({"idempotency_key": "Key reused for different payment."})
        return previous
    source_order_id = _source_order(
        owner=owner,
        source_order_id=source_order_id,
        currency=currency,
        amount_minor=amount_minor,
    )
    payment = PaymentIntent.objects.create(
        owner=owner,
        amount_minor=amount_minor,
        currency=currency,
        source_order_id=source_order_id,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
    )
    record_audit_event(
        actor=owner,
        action="payments.intent.created",
        target_type="payments.PaymentIntent",
        target_id=payment.pk,
        changes={"currency": currency, "amount_minor": amount_minor},
    )
    return payment


@transaction.atomic
def cancel_intent(*, actor, payment_id):
    owner = _owner(actor)
    payment = PaymentIntent.objects.select_for_update().filter(pk=payment_id, owner=owner).first()
    if payment is None:
        raise NotFound()
    if not can_cancel(payment.status):
        raise ValidationError({"status": "Only pending payments can be canceled."})
    payment.status = PaymentIntent.Status.CANCELED
    payment.save(update_fields=("status", "updated_at"))
    record_audit_event(
        actor=owner,
        action="payments.intent.canceled",
        target_type="payments.PaymentIntent",
        target_id=payment.pk,
    )
    return payment


@transaction.atomic
def reconcile_manual(*, actor, payment_id, event_key, outcome, amount_minor, currency):
    """Dev/manual adapter: only global superuser may attest trusted payment evidence."""
    if not actor or not actor.is_authenticated or not actor.is_active or not actor.is_superuser:
        raise PermissionDenied("Payment reconciliation is restricted to superusers.")
    try:
        validate_money(currency, amount_minor)
    except PaymentRuleViolation as exc:
        raise ValidationError({"amount_minor": str(exc)}) from exc
    base = PaymentIntent.objects.filter(pk=payment_id).values("owner_id").first()
    if not base:
        raise NotFound()
    # Same lock order as create/cancel and Orders transitions: user then payment.
    owner = get_user_model().objects.select_for_update().get(pk=base["owner_id"])
    payment = PaymentIntent.objects.select_for_update().get(pk=payment_id, owner=owner)
    event = PaymentEvent.objects.filter(event_key=event_key).first()
    if event:
        if (
            event.intent_id != payment.pk
            or event.outcome != outcome
            or event.amount_minor != amount_minor
            or event.currency != currency
        ):
            raise ValidationError({"event_key": "Event key conflicts with prior settlement."})
        return payment
    if not can_reconcile(payment.status, outcome):
        raise ValidationError({"status": "Payment is not pending or outcome is unsupported."})
    if payment.amount_minor != amount_minor or payment.currency != currency:
        raise ValidationError({"amount_minor": "Settlement amount/currency mismatch."})
    if outcome == "succeeded" and payment.source_order_id is not None:
        if (
            PaymentIntent.objects.filter(
                owner=owner, source_order_id=payment.source_order_id, status="succeeded"
            )
            .exclude(pk=payment.pk)
            .exists()
        ):
            raise ValidationError(
                {"source_order_id": "This order already has a successful payment."}
            )
        _source_order(
            owner=owner,
            source_order_id=payment.source_order_id,
            currency=currency,
            amount_minor=amount_minor,
        )
    payment.status = outcome
    payment.settled_at = timezone.now()
    payment.save(update_fields=("status", "settled_at", "updated_at"))
    PaymentEvent.objects.create(
        intent=payment,
        event_key=event_key,
        outcome=outcome,
        amount_minor=amount_minor,
        currency=currency,
        verified_by=actor,
    )
    record_audit_event(
        actor=actor,
        action="payments.intent.reconciled",
        target_type="payments.PaymentIntent",
        target_id=payment.pk,
        changes={"outcome": outcome, "amount_minor": amount_minor},
    )
    return payment
