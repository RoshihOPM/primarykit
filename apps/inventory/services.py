"""Stock services: PostgreSQL row locks, invariants, ledger and request idempotency."""

import hashlib
import json

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.audit import record_audit_event
from apps.organizations.models import BranchAccess, Organization
from apps.organizations.permissions import get_active_membership
from apps.organizations.scoping import require_warehouse_access, require_writer

from .models import (
    InventoryOperation,
    StockBalance,
    StockMovement,
    StockReservation,
)


def _balance_dict(balance):
    return {
        "warehouse_id": str(balance.warehouse_id),
        "item_id": str(balance.item_id),
        "on_hand": balance.on_hand,
        "reserved": balance.reserved,
        "available": balance.available,
    }


def _locked_balances(organization, pairs):
    """Create missing zero rows, then lock in stable UUID order to avoid deadlocks."""
    identifiers = []
    for warehouse, item in sorted(pairs, key=lambda pair: (str(pair[0].pk), str(pair[1].pk))):
        obj, _ = StockBalance.objects.get_or_create(
            organization=organization, warehouse=warehouse, item=item
        )
        identifiers.append(obj.pk)
    rows = list(
        StockBalance.objects.select_for_update()
        .filter(organization=organization, pk__in=identifiers)
        .order_by("pk")
    )
    return {(row.warehouse_id, row.item_id): row for row in rows}


def _apply(*, balance, physical=0, held=0, operation):
    new_hand = balance.on_hand + physical
    new_reserved = balance.reserved + held
    if new_hand < 0 or new_reserved < 0 or new_reserved > new_hand:
        raise ValidationError({"stock": "Insufficient available or reserved quantity."})
    balance.on_hand = new_hand
    balance.reserved = new_reserved
    balance.save(update_fields=("on_hand", "reserved", "updated_at"))
    StockMovement.objects.create(
        operation=operation,
        balance=balance,
        kind=operation.kind,
        on_hand_delta=physical,
        reserved_delta=held,
    )


def _execute_locked(organization, operation, data, actor):
    kind = operation.kind
    if kind in {"receive", "issue", "reserve", "transfer"}:
        warehouse = data["warehouse"]
        item = data["item"]
        if not warehouse.is_active or not item.is_active or not item.category.is_active:
            raise ValidationError({"stock": "Inactive warehouse or catalog item."})
        pairs = [(warehouse, item)]
        if kind == "transfer":
            destination = data["destination"]
            if not destination.is_active or destination.pk == warehouse.pk:
                raise ValidationError(
                    {"destination": "Destination must be a different active warehouse."}
                )
            pairs.append((destination, item))
        locked = _locked_balances(organization, pairs)
        balance = locked[(warehouse.pk, item.pk)]
        quantity = data["quantity"]
        result = {"balances": []}
        if kind == "receive":
            _apply(balance=balance, physical=quantity, operation=operation)
        elif kind == "issue":
            _apply(balance=balance, physical=-quantity, operation=operation)
        elif kind == "reserve":
            _apply(balance=balance, held=quantity, operation=operation)
            reservation = StockReservation.objects.create(
                balance=balance,
                quantity=quantity,
                created_by=actor,
            )
            result["reservation_id"] = str(reservation.pk)
        else:
            target = locked[(destination.pk, item.pk)]
            _apply(balance=balance, physical=-quantity, operation=operation)
            _apply(balance=target, physical=quantity, operation=operation)
            result["balances"].append(_balance_dict(target))
        result["balances"].insert(0, _balance_dict(balance))
        return result
    reservation = data["reservation"]
    balance = _locked_balances(
        organization, [(reservation.balance.warehouse, reservation.balance.item)]
    )[(reservation.balance.warehouse_id, reservation.balance.item_id)]
    # All operations on reservations lock balance BEFORE reservation to avoid deadlocks.
    current = StockReservation.objects.select_for_update().get(pk=reservation.pk)
    if current.status != StockReservation.Status.ACTIVE:
        raise ValidationError({"reservation": "Reservation is already closed."})
    quantity = current.quantity
    if kind == "release":
        _apply(balance=balance, held=-quantity, operation=operation)
        current.status = StockReservation.Status.RELEASED
    else:
        _apply(balance=balance, physical=-quantity, held=-quantity, operation=operation)
        current.status = StockReservation.Status.CONSUMED
    current.closed_at = timezone.now()
    current.save(update_fields=("status", "closed_at", "updated_at"))
    return {"reservation_id": str(current.pk), "balances": [_balance_dict(balance)]}


def _assert_command_tenant(organization, membership, data):
    """Verify FK consistency and role/branch grants even when invoked outside DRF."""
    kind = data["kind"]
    if kind in {"receive", "issue", "reserve", "transfer"}:
        warehouse = data["warehouse"]
        item = data["item"]
        if (
            item.organization_id != organization.pk
            or item.category.organization_id != organization.pk
        ):
            raise NotFound()
        if not item.is_active or not item.category.is_active:
            raise ValidationError({"item": "Inactive item."})
        require_warehouse_access(membership=membership, warehouse=warehouse, writing=True)
        if kind == "transfer":
            destination = data["destination"]
            require_warehouse_access(membership=membership, warehouse=destination, writing=True)
            if destination.pk == warehouse.pk:
                raise ValidationError({"destination": "Must be a different warehouse."})
    else:
        reservation = data["reservation"]
        balance = reservation.balance
        warehouse = balance.warehouse
        if (
            balance.organization_id != organization.pk
            or warehouse.organization_id != organization.pk
            or balance.item.organization_id != organization.pk
        ):
            raise NotFound()
        # Existing reservations may be closed after a warehouse is deactivated.
        if (
            membership.role not in ("owner", "admin")
            and not BranchAccess.objects.filter(
                membership=membership,
                branch_id=warehouse.branch_id,
                branch__organization=organization,
            ).exists()
        ):
            raise NotFound()


def execute_stock_operation(*, actor, organization, data):
    """Idempotent atomic command with locked tenant and branch authorization."""
    kind = data["kind"]
    key = data["idempotency_key"]
    canonical = {
        field: (str(value.pk) if hasattr(value, "pk") else value)
        for field, value in data.items()
        if field != "idempotency_key"
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    try:
        with transaction.atomic():
            locked_org = Organization.objects.select_for_update().get(pk=organization.pk)
            membership = get_active_membership(user=actor, organization=locked_org)
            require_writer(membership)
            _assert_command_tenant(locked_org, membership, data)
            operation = InventoryOperation.objects.create(
                organization=locked_org,
                key=key,
                fingerprint=fingerprint,
                kind=kind,
                created_by=actor,
            )
            result = _execute_locked(locked_org, operation, data, actor)
            result.update({"operation_id": str(operation.pk), "kind": kind})
            operation.result = result
            operation.save(update_fields=("result", "updated_at"))
            record_audit_event(
                actor=actor,
                action="inventory.operation.recorded",
                target_type="inventory.InventoryOperation",
                target_id=operation.pk,
                changes={"kind": kind, "quantity": data.get("quantity") or 0},
            )
            return result
    except IntegrityError:
        existing = InventoryOperation.objects.filter(organization=organization, key=key).first()
        if existing is None:
            raise
        if existing.fingerprint != fingerprint or existing.created_by_id != actor.pk:
            raise ValidationError(
                {"idempotency_key": "Key has already been used for a different request."}
            ) from None
        # Deny replay if membership/branch access was revoked since original write.
        with transaction.atomic():
            locked_org = Organization.objects.select_for_update().get(pk=organization.pk)
            membership = get_active_membership(user=actor, organization=locked_org)
            require_writer(membership)
            _assert_command_tenant(locked_org, membership, data)
        return existing.result
