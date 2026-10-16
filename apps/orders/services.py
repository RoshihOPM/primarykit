"""Application commands: strict ownership, price snapshots and idempotency."""

import hashlib
import json

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.audit import record_audit_event

from .domain import OrderRuleViolation, may_cancel_order, normalize_order_lines
from .models import Order, OrderItem


def _lock_owner(actor):
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise NotFound()
    owner = get_user_model().objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if owner is None:
        raise NotFound()
    return owner


@transaction.atomic
def place_order(*, actor, currency, lines, idempotency_key):
    try:
        normalized, total = normalize_order_lines(currency, lines)
    except OrderRuleViolation as exc:
        raise ValidationError({"lines": str(exc)}) from exc
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "currency": currency,
                "lines": [
                    {
                        "sku": row.sku,
                        "title": row.title,
                        "quantity": row.quantity,
                        "unit_price_minor": row.unit_price_minor,
                    }
                    for row in normalized
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    owner = _lock_owner(actor)
    previous = Order.objects.filter(owner=owner, idempotency_key=idempotency_key).first()
    if previous:
        if previous.fingerprint != fingerprint:
            raise ValidationError({"idempotency_key": "Key reused for different order."})
        return previous
    order = Order.objects.create(
        owner=owner,
        currency=currency,
        total_minor=total,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
    )
    OrderItem.objects.bulk_create(
        [
            OrderItem(
                order=order,
                sku=line.sku,
                title=line.title,
                quantity=line.quantity,
                unit_price_minor=line.unit_price_minor,
                line_total_minor=line.total_minor,
            )
            for line in normalized
        ]
    )
    record_audit_event(
        actor=owner,
        action="orders.order.placed",
        target_type="orders.Order",
        target_id=order.pk,
        changes={"total_minor": total, "currency": currency},
    )
    return order


@transaction.atomic
def cancel_order(*, actor, order_id):
    owner = _lock_owner(actor)
    order = Order.objects.select_for_update().filter(pk=order_id, owner=owner).first()
    if order is None:
        raise NotFound()
    if not may_cancel_order(order.status):
        raise ValidationError({"status": "Only placed orders can be canceled."})
    # Cancellation of a paid order needs provider refunds and is not supported here.
    # The optional Payments integration must be checked while holding owner lock.
    from django.apps import apps

    if apps.is_installed("apps.sales"):
        from apps.sales.models import Sale

        if Sale.objects.filter(owner=owner, source_order_id=order.pk, status="recorded").exists():
            raise ValidationError({"status": "Order has a recorded sale and cannot be canceled."})
    if apps.is_installed("apps.payments"):
        from apps.payments.models import PaymentIntent

        if PaymentIntent.objects.filter(
            owner=owner, source_order_id=order.pk, status="succeeded"
        ).exists():
            raise ValidationError({"status": "Paid order cannot be canceled without a refund."})
    order.status = Order.Status.CANCELED
    order.canceled_at = timezone.now()
    order.save(update_fields=("status", "canceled_at", "updated_at"))
    record_audit_event(
        actor=owner,
        action="orders.order.canceled",
        target_type="orders.Order",
        target_id=order.pk,
    )
    return order
