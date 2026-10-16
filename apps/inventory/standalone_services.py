"""Standalone stock commands: transactional owner security, ledger and idempotency."""

import hashlib
import json

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.audit import record_audit_event

from .domain import (
    StockPosition,
    StockRuleViolation,
    require_open_reservation,
    validate_command_quantity,
    validate_command_shape,
)
from .models import (
    InventoryOperation,
    StockBalance,
    StockMovement,
    StockReservation,
)


def _require_owner(actor, data):
    """Never rely only on DRF queryset filtering: service callers get the same IDOR checks."""
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise NotFound()
    kind = data["kind"]
    if kind in {"receive", "issue", "reserve", "transfer"}:
        warehouse = data["warehouse"]
        item = data["item"]
        if warehouse.owner_id != actor.pk or item.owner_id != actor.pk:
            raise NotFound()
        if not warehouse.is_active or not item.is_active:
            raise ValidationError({"stock": "Inactive warehouse or inventory item."})
        if kind == "transfer":
            destination = data["destination"]
            if destination.owner_id != actor.pk:
                raise NotFound()
            if not destination.is_active or destination.pk == warehouse.pk:
                raise ValidationError({"destination": "A different active warehouse is required."})
    else:
        reservation = data["reservation"]
        if reservation.balance.owner_id != actor.pk:
            raise NotFound()
        if reservation.balance.warehouse.owner_id != actor.pk:
            raise NotFound()
        if reservation.balance.item.owner_id != actor.pk:
            raise NotFound()


def _balance_dict(balance):
    return {
        "warehouse_id": str(balance.warehouse_id),
        "item_id": str(balance.item_id),
        "on_hand": balance.on_hand,
        "reserved": balance.reserved,
        "available": balance.available,
    }


def _locked_balances(actor, pairs):
    ids = []
    for warehouse, item in sorted(pairs, key=lambda p: (str(p[0].pk), str(p[1].pk))):
        row, _ = StockBalance.objects.get_or_create(
            owner=actor, warehouse=warehouse, item=item
        )
        ids.append(row.pk)
    balances = list(
        StockBalance.objects.select_for_update()
        .filter(owner=actor, pk__in=ids)
        .order_by("pk")
    )
    return {(row.warehouse_id, row.item_id): row for row in balances}


def _apply(*, balance, operation, physical=0, held=0):
    try:
        updated = StockPosition(balance.on_hand, balance.reserved).apply(
            physical=physical, held=held
        )
    except StockRuleViolation as exc:
        raise ValidationError({"stock": str(exc)}) from exc
    balance.on_hand = updated.on_hand
    balance.reserved = updated.reserved
    balance.save(update_fields=("on_hand", "reserved", "updated_at"))
    StockMovement.objects.create(
        operation=operation,
        balance=balance,
        kind=operation.kind,
        on_hand_delta=physical,
        reserved_delta=held,
    )


def _execute_locked(actor, operation, data):
    kind = operation.kind
    if kind in {"receive", "issue", "reserve", "transfer"}:
        warehouse, item = data["warehouse"], data["item"]
        pairs = [(warehouse, item)]
        if kind == "transfer":
            pairs.append((data["destination"], item))
        balances = _locked_balances(actor, pairs)
        balance = balances[(warehouse.pk, item.pk)]
        quantity = data["quantity"]
        result = {"balances": []}
        if kind == "receive":
            _apply(balance=balance, physical=quantity, operation=operation)
        elif kind == "issue":
            _apply(balance=balance, physical=-quantity, operation=operation)
        elif kind == "reserve":
            _apply(balance=balance, held=quantity, operation=operation)
            reservation = StockReservation.objects.create(
                balance=balance, quantity=quantity, created_by=actor
            )
            result["reservation_id"] = str(reservation.pk)
        else:
            destination = balances[(data["destination"].pk, item.pk)]
            _apply(balance=balance, physical=-quantity, operation=operation)
            _apply(balance=destination, physical=quantity, operation=operation)
            result["balances"].append(_balance_dict(destination))
        result["balances"].insert(0, _balance_dict(balance))
        return result

    reservation = data["reservation"]
    item = reservation.balance.item
    warehouse = reservation.balance.warehouse
    balance = _locked_balances(actor, [(warehouse, item)])[(warehouse.pk, item.pk)]
    current = StockReservation.objects.select_for_update().get(pk=reservation.pk)
    try:
        require_open_reservation(current.status)
    except StockRuleViolation as exc:
        raise ValidationError({"reservation": str(exc)}) from exc
    if kind == "release":
        _apply(balance=balance, held=-current.quantity, operation=operation)
        current.status = StockReservation.Status.RELEASED
    else:
        _apply(
            balance=balance,
            physical=-current.quantity,
            held=-current.quantity,
            operation=operation,
        )
        current.status = StockReservation.Status.CONSUMED
    current.closed_at = timezone.now()
    current.save(update_fields=("status", "closed_at", "updated_at"))
    return {"reservation_id": str(current.pk), "balances": [_balance_dict(balance)]}


def execute_stock_operation(*, actor, data, organization=None):
    """Apply a personal stock command under actor row lock and idempotent operation key."""
    kind = data["kind"]
    try:
        validate_command_shape(kind, data)
        validate_command_quantity(kind, data)
    except StockRuleViolation as exc:
        raise ValidationError({"detail": str(exc)}) from exc

    canonical = {
        name: str(value.pk) if hasattr(value, "pk") else value
        for name, value in data.items()
        if name != "idempotency_key"
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    key = data["idempotency_key"]

    def lock_actor():
        locked = get_user_model().objects.select_for_update().filter(
            pk=actor.pk, is_active=True
        ).first()
        if locked is None:
            raise NotFound()
        _require_owner(locked, data)
        return locked

    try:
        with transaction.atomic():
            owner = lock_actor()
            operation = InventoryOperation.objects.create(
                owner=owner,
                key=key,
                fingerprint=fingerprint,
                kind=kind,
                created_by=owner,
            )
            result = _execute_locked(owner, operation, data)
            result.update({"operation_id": str(operation.pk), "kind": kind})
            operation.result = result
            operation.save(update_fields=("result", "updated_at"))
            record_audit_event(
                actor=owner,
                action="inventory.operation.recorded",
                target_type="inventory.InventoryOperation",
                target_id=operation.pk,
                changes={"kind": kind, "quantity": data.get("quantity") or 0},
            )
            return result
    except IntegrityError:
        existing = InventoryOperation.objects.filter(owner_id=actor.pk, key=key).first()
        if existing is None:
            raise
        if existing.fingerprint != fingerprint or existing.created_by_id != actor.pk:
            raise ValidationError(
                {"idempotency_key": "Key has already been used for a different request."}
            ) from None
        with transaction.atomic():
            lock_actor()
        return existing.result
