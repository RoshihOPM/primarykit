"""Idempotent sale recording; do not silently capture payment or decrement stock."""

import hashlib
import json
import uuid

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.audit import record_audit_event

from .domain import SalesRuleViolation, normalize_sale_lines
from .models import Sale, SaleLineItem


def _lock_owner(actor):
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise NotFound()
    owner = get_user_model().objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if owner is None:
        raise NotFound()
    return owner


@transaction.atomic
def record_sale(*, actor, currency, lines, idempotency_key, source_order_id=None):
    try:
        normalized, total = normalize_sale_lines(currency, lines)
    except SalesRuleViolation as exc:
        raise ValidationError({"lines": str(exc)}) from exc
    if source_order_id is not None:
        if not apps.is_installed("apps.orders"):
            raise ValidationError({"source_order_id": "Orders module is not installed."})
        try:
            source_order_id = uuid.UUID(str(source_order_id))
        except (ValueError, TypeError) as exc:
            raise ValidationError({"source_order_id": "Invalid order identifier."}) from exc
    payload = {
        "currency": currency,
        "source_order_id": str(source_order_id),
        "lines": [vars(line) for line in normalized],
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    owner = _lock_owner(actor)
    previous = Sale.objects.filter(owner=owner, idempotency_key=idempotency_key).first()
    if previous:
        if previous.fingerprint != fingerprint:
            raise ValidationError({"idempotency_key": "Key reused with different sale."})
        return previous
    if source_order_id:
        from apps.orders.models import Order

        order = (
            Order.objects.select_for_update()
            .filter(pk=source_order_id, owner=owner, status="placed")
            .first()
        )
        if order is None:
            raise NotFound()
        if order.currency != currency or order.total_minor != total:
            raise ValidationError({"source_order_id": "Sale must match order currency and total."})
        order_lines = list(
            order.items.order_by("pk").values_list(
                "sku", "title", "quantity", "unit_price_minor"
            )
        )
        sale_lines = [
            (line.sku, line.title, line.quantity, line.unit_price_minor)
            for line in normalized
        ]
        if order_lines != sale_lines:
            raise ValidationError({"source_order_id": "Sale lines must match order snapshot."})
        if Sale.objects.filter(owner=owner, source_order_id=source_order_id).exists():
            raise ValidationError({"source_order_id": "Order already recorded as a sale."})
    sale = Sale.objects.create(
        owner=owner,
        currency=currency,
        total_minor=total,
        source_order_id=source_order_id,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
    )
    SaleLineItem.objects.bulk_create(
        [
            SaleLineItem(
                sale=sale,
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
        action="sales.sale.recorded",
        target_type="sales.Sale",
        target_id=sale.pk,
        changes={"total_minor": total, "currency": currency},
    )
    return sale


@transaction.atomic
def void_sale(*, actor, sale_id):
    owner = _lock_owner(actor)
    sale = Sale.objects.select_for_update().filter(pk=sale_id, owner=owner).first()
    if sale is None:
        raise NotFound()
    if sale.status != Sale.Status.RECORDED:
        raise ValidationError({"status": "Sale already voided."})
    sale.status = Sale.Status.VOIDED
    sale.voided_at = timezone.now()
    sale.save(update_fields=("status", "voided_at", "updated_at"))
    record_audit_event(
        actor=owner, action="sales.sale.voided", target_type="sales.Sale", target_id=sale.pk
    )
    return sale
