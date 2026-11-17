# ruff: noqa: E402
"""Standalone Inventory under independent PostgreSQL writers (not a SQLite simulation).

Every worker runs on its own database connection and is released by a barrier, so the
owner row lock, the balance row locks and the idempotency constraint are really contended.
The suite executes only in a generated standalone project on PostgreSQL.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.conf import settings

if settings.INVENTORY_MODE != "standalone":
    pytest.skip("Personal Inventory schema not selected", allow_module_level=True)

from django.apps import apps
from django.db import close_old_connections, connection, connections
from django.db.models import Sum
from rest_framework.exceptions import NotFound, ValidationError

from apps.inventory.models import (
    InventoryItem,
    InventoryOperation,
    StockBalance,
    StockMovement,
    StockReservation,
    Warehouse,
)
from apps.inventory.services import execute_stock_operation
from apps.users.models import User

pytestmark = pytest.mark.django_db(transaction=True)

WAIT_SECONDS = 15
OK, REJECTED, HIDDEN = "ok", "rejected", "not_found"


@pytest.fixture(autouse=True)
def _postgresql_only():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row-lock test requires PostgreSQL")


def _user(email, *, superuser=False):
    return User.objects.create_user(
        email=email,
        password="Concurrent-standalone-password-111",
        email_verified=True,
        is_staff=superuser,
        is_superuser=superuser,
    )


def _stock(email, *, on_hand=0, reserved=0):
    owner = _user(email)
    item = InventoryItem.objects.create(owner=owner, sku="RACE-1", name="Raced item")
    warehouse = Warehouse.objects.create(owner=owner, code="main", name="Main")
    spare = Warehouse.objects.create(owner=owner, code="spare", name="Spare")
    balance = None
    if on_hand or reserved:
        balance = StockBalance.objects.create(
            owner=owner, warehouse=warehouse, item=item, on_hand=on_hand, reserved=reserved
        )
    return {
        "owner": owner,
        "item": item,
        "warehouse": warehouse,
        "spare": spare,
        "balance": balance,
    }


def _entry(stock, kind, key, quantity, **extra):
    return {
        "kind": kind,
        "idempotency_key": key,
        "warehouse": stock["warehouse"],
        "item": stock["item"],
        "quantity": quantity,
        **extra,
    }


def _race(*commands):
    """Run (actor, data) commands simultaneously, one PostgreSQL connection per thread.

    Only the documented rejections are captured; a deadlock, lock timeout or any other
    unexpected error propagates and fails the test.
    """
    barrier = Barrier(len(commands))

    def worker(command):
        actor, data = command
        close_old_connections()
        try:
            barrier.wait(timeout=WAIT_SECONDS)
            return OK, execute_stock_operation(actor=actor, data=data)
        except NotFound as exc:
            return HIDDEN, exc
        except ValidationError as exc:
            return REJECTED, exc
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(commands)) as pool:
        futures = [pool.submit(worker, command) for command in commands]
        return [future.result(timeout=WAIT_SECONDS * 4) for future in futures]


def _statuses(outcomes):
    return sorted(status for status, _ in outcomes)


def _assert_ledger_consistent(*, opening=None, operations):
    """Balances are never negative and equal opening stock plus their immutable movements."""
    opening = opening or {}
    for balance in StockBalance.objects.all():
        assert 0 <= balance.reserved <= balance.on_hand
        totals = StockMovement.objects.filter(balance=balance).aggregate(
            hand=Sum("on_hand_delta"), held=Sum("reserved_delta")
        )
        start_hand, start_held = opening.get(balance.pk, (0, 0))
        assert balance.on_hand == start_hand + (totals["hand"] or 0)
        assert balance.reserved == start_held + (totals["held"] or 0)
    # A rejected command must roll back its operation row together with its movements.
    assert InventoryOperation.objects.count() == operations
    assert not StockMovement.objects.filter(operation__isnull=True).exists()
    assert set(StockMovement.objects.values_list("operation_id", flat=True)) == set(
        InventoryOperation.objects.values_list("pk", flat=True)
    )
    if apps.is_installed("apps.audit"):
        audit = apps.get_model("audit", "AuditEvent")
        assert audit.objects.filter(action="inventory.operation.recorded").count() == operations


def test_two_writers_cannot_overdraw_the_same_standalone_balance():
    stock = _stock("race-overdraw@standalone.test", on_hand=5)
    owner, balance = stock["owner"], stock["balance"]

    outcomes = _race(
        (owner, _entry(stock, "issue", "overdraw-issue-1", 4)),
        (owner, _entry(stock, "issue", "overdraw-issue-2", 4)),
    )

    assert _statuses(outcomes) == [OK, REJECTED]
    balance.refresh_from_db()
    assert (balance.on_hand, balance.reserved) == (1, 0)
    winner = next(result for status, result in outcomes if status == OK)
    assert winner["balances"][0]["on_hand"] == 1
    movement = StockMovement.objects.get()
    assert (movement.on_hand_delta, movement.reserved_delta) == (-4, 0)
    assert str(movement.operation_id) == winner["operation_id"]
    _assert_ledger_consistent(opening={balance.pk: (5, 0)}, operations=1)


def test_burst_of_writers_drains_stock_exactly_without_going_negative():
    stock = _stock("race-burst@standalone.test", on_hand=10)
    owner, balance = stock["owner"], stock["balance"]

    outcomes = _race(
        *((owner, _entry(stock, "issue", f"burst-issue-{number}", 3)) for number in range(8))
    )

    assert _statuses(outcomes) == [OK] * 3 + [REJECTED] * 5
    balance.refresh_from_db()
    assert (balance.on_hand, balance.reserved) == (1, 0)
    # Each winner saw a distinct serialized balance: no lost update between writers.
    assert sorted(
        result["balances"][0]["on_hand"] for status, result in outcomes if status == OK
    ) == [1, 4, 7]
    assert StockMovement.objects.count() == 3
    _assert_ledger_consistent(opening={balance.pk: (10, 0)}, operations=3)


def test_concurrent_first_receipts_create_one_balance_row():
    stock = _stock("race-first-receipt@standalone.test")
    owner = stock["owner"]

    outcomes = _race(
        *((owner, _entry(stock, "receive", f"first-receipt-{number}", 2)) for number in range(4))
    )

    assert _statuses(outcomes) == [OK] * 4
    balance = StockBalance.objects.get()
    assert (balance.owner_id, balance.on_hand, balance.reserved) == (owner.pk, 8, 0)
    _assert_ledger_consistent(operations=4)


def test_same_idempotency_key_has_one_effect_and_both_callers_see_one_result():
    stock = _stock("race-replay@standalone.test", on_hand=10)
    owner, balance = stock["owner"], stock["balance"]

    outcomes = _race(*((owner, _entry(stock, "issue", "replayed-issue-key", 4)) for _ in range(2)))

    assert _statuses(outcomes) == [OK, OK]
    first, second = (result for _, result in outcomes)
    assert first == second
    operation = InventoryOperation.objects.get()
    assert (operation.owner_id, operation.key) == (owner.pk, "replayed-issue-key")
    assert first == operation.result
    assert first["operation_id"] == str(operation.pk)
    assert first["balances"] == [
        {
            "warehouse_id": str(stock["warehouse"].pk),
            "item_id": str(stock["item"].pk),
            "on_hand": 6,
            "reserved": 0,
            "available": 6,
        }
    ]
    balance.refresh_from_db()
    assert (balance.on_hand, balance.reserved) == (6, 0)
    assert StockMovement.objects.count() == 1
    _assert_ledger_consistent(opening={balance.pk: (10, 0)}, operations=1)


def test_many_replays_of_one_reservation_key_create_one_reservation():
    stock = _stock("race-replay-reserve@standalone.test", on_hand=10)
    owner, balance = stock["owner"], stock["balance"]

    outcomes = _race(
        *((owner, _entry(stock, "reserve", "replayed-reserve-key", 3)) for _ in range(6))
    )

    assert _statuses(outcomes) == [OK] * 6
    results = [result for _, result in outcomes]
    assert all(result == results[0] for result in results)
    reservation = StockReservation.objects.get()
    assert results[0]["reservation_id"] == str(reservation.pk)
    assert (reservation.quantity, reservation.status) == (3, "active")
    balance.refresh_from_db()
    assert (balance.on_hand, balance.reserved) == (10, 3)
    assert StockMovement.objects.count() == 1
    _assert_ledger_consistent(opening={balance.pk: (10, 0)}, operations=1)


def test_one_key_raced_by_two_different_requests_applies_only_one_of_them():
    stock = _stock("race-key-conflict@standalone.test", on_hand=10)
    owner, balance = stock["owner"], stock["balance"]

    outcomes = _race(
        (owner, _entry(stock, "issue", "conflicting-key", 2)),
        (owner, _entry(stock, "issue", "conflicting-key", 5)),
    )

    assert _statuses(outcomes) == [OK, REJECTED]
    loser = next(error for status, error in outcomes if status == REJECTED)
    assert "idempotency_key" in loser.detail
    winner = next(result for status, result in outcomes if status == OK)
    applied = 10 - winner["balances"][0]["on_hand"]
    assert applied in (2, 5)
    balance.refresh_from_db()
    assert (balance.on_hand, balance.reserved) == (10 - applied, 0)
    assert StockMovement.objects.get().on_hand_delta == -applied
    _assert_ledger_consistent(opening={balance.pk: (10, 0)}, operations=1)


def test_reservation_and_issue_cannot_both_take_the_same_available_stock():
    stock = _stock("race-reserve-issue@standalone.test", on_hand=5)
    owner, balance = stock["owner"], stock["balance"]

    reserve, issue = _race(
        (owner, _entry(stock, "reserve", "reserve-vs-issue-hold", 4)),
        (owner, _entry(stock, "issue", "reserve-vs-issue-ship", 4)),
    )

    assert _statuses([reserve, issue]) == [OK, REJECTED]
    balance.refresh_from_db()
    if reserve[0] == OK:
        assert (balance.on_hand, balance.reserved, balance.available) == (5, 4, 1)
        held = StockReservation.objects.get()
        assert (held.balance_id, held.quantity, held.status) == (balance.pk, 4, "active")
        assert reserve[1]["reservation_id"] == str(held.pk)
    else:
        assert (balance.on_hand, balance.reserved, balance.available) == (1, 0, 1)
        assert not StockReservation.objects.exists()
    assert StockMovement.objects.count() == 1
    _assert_ledger_consistent(opening={balance.pk: (5, 0)}, operations=1)


def _reserved(stock, quantity, key="prepared-reservation"):
    result = execute_stock_operation(
        actor=stock["owner"], data=_entry(stock, "reserve", key, quantity)
    )
    return StockReservation.objects.select_related("balance__warehouse", "balance__item").get(
        pk=result["reservation_id"]
    )


def test_issue_racing_a_release_never_ships_stock_that_is_still_reserved():
    stock = _stock("race-release-issue@standalone.test", on_hand=5)
    owner, balance = stock["owner"], stock["balance"]
    reservation = _reserved(stock, 4)

    release, issue = _race(
        (
            owner,
            {"kind": "release", "idempotency_key": "release-vs-issue", "reservation": reservation},
        ),
        (owner, _entry(stock, "issue", "issue-vs-release", 2)),
    )

    # The release always fits; the issue fits only when it was serialized after the release.
    assert release[0] == OK
    balance.refresh_from_db()
    reservation.refresh_from_db()
    assert reservation.status == "released"
    if issue[0] == OK:
        assert (balance.on_hand, balance.reserved) == (3, 0)
        assert issue[1]["balances"][0]["on_hand"] == 3
    else:
        assert issue[0] == REJECTED
        assert (balance.on_hand, balance.reserved) == (5, 0)
    _assert_ledger_consistent(opening={balance.pk: (5, 0)}, operations=3 if issue[0] == OK else 2)


def test_release_and_consume_close_one_reservation_exactly_once():
    stock = _stock("race-close@standalone.test", on_hand=5)
    owner, balance = stock["owner"], stock["balance"]
    reservation = _reserved(stock, 4)

    release, consume = _race(
        (
            owner,
            {"kind": "release", "idempotency_key": "close-by-release", "reservation": reservation},
        ),
        (
            owner,
            {"kind": "consume", "idempotency_key": "close-by-consume", "reservation": reservation},
        ),
    )

    assert _statuses([release, consume]) == [OK, REJECTED]
    balance.refresh_from_db()
    reservation.refresh_from_db()
    assert reservation.closed_at is not None
    if consume[0] == OK:
        assert reservation.status == "consumed"
        assert (balance.on_hand, balance.reserved) == (1, 0)
    else:
        assert reservation.status == "released"
        assert (balance.on_hand, balance.reserved) == (5, 0)
    assert StockMovement.objects.count() == 2
    _assert_ledger_consistent(opening={balance.pk: (5, 0)}, operations=2)


def test_opposing_transfers_do_not_deadlock_and_conserve_stock():
    stock = _stock("race-transfer@standalone.test", on_hand=5)
    owner, item, main, spare = stock["owner"], stock["item"], stock["warehouse"], stock["spare"]
    other = StockBalance.objects.create(owner=owner, warehouse=spare, item=item, on_hand=5)

    def transfer(number, source, destination):
        return (
            owner,
            {
                "kind": "transfer",
                "idempotency_key": f"opposing-transfer-{number}",
                "warehouse": source,
                "item": item,
                "destination": destination,
                "quantity": 2,
            },
        )

    outcomes = _race(
        *(
            transfer(number, *((main, spare) if number % 2 else (spare, main)))
            for number in range(6)
        )
    )

    assert _statuses(outcomes) == [OK] * 6
    stock["balance"].refresh_from_db()
    other.refresh_from_db()
    assert (stock["balance"].on_hand, other.on_hand) == (5, 5)
    assert StockMovement.objects.count() == 12
    assert StockMovement.objects.aggregate(total=Sum("on_hand_delta"))["total"] == 0
    opening = {stock["balance"].pk: (5, 0), other.pk: (5, 0)}
    _assert_ledger_consistent(opening=opening, operations=6)


def test_foreign_owners_racing_the_owner_are_rejected_and_change_nothing():
    stock = _stock("race-victim@standalone.test", on_hand=5)
    owner, balance = stock["owner"], stock["balance"]
    reservation = _reserved(stock, 1)
    intruder = _user("race-intruder@standalone.test")
    root = _user("race-root@standalone.test", superuser=True)
    owner_issue = _entry(stock, "issue", "shared-looking-key", 2)

    outcomes = _race(
        (owner, owner_issue),
        # Identical payload and key: must not replay or reveal the owner's operation.
        (intruder, dict(owner_issue)),
        (intruder, _entry(stock, "receive", "intruder-receive", 50)),
        (intruder, _entry(stock, "reserve", "intruder-reserve", 1)),
        (intruder, _entry(stock, "transfer", "intruder-move", 1, destination=stock["spare"])),
        (
            intruder,
            {"kind": "consume", "idempotency_key": "intruder-consume", "reservation": reservation},
        ),
        # No implicit Django superuser bypass in standalone mode.
        (root, _entry(stock, "issue", "root-issue", 1)),
        (
            root,
            {"kind": "release", "idempotency_key": "root-release", "reservation": reservation},
        ),
    )

    assert [status for status, _ in outcomes] == [OK] + [HIDDEN] * 7
    balance.refresh_from_db()
    reservation.refresh_from_db()
    assert (balance.on_hand, balance.reserved) == (3, 1)
    assert (reservation.status, reservation.closed_at) == ("active", None)
    assert StockBalance.objects.count() == 1
    assert StockReservation.objects.count() == 1
    foreign = (intruder.pk, root.pk)
    assert not InventoryOperation.objects.filter(owner_id__in=foreign).exists()
    assert not InventoryOperation.objects.filter(created_by_id__in=foreign).exists()
    assert not StockBalance.objects.filter(owner_id__in=foreign).exists()
    assert set(InventoryOperation.objects.values_list("owner_id", flat=True)) == {owner.pk}
    if apps.is_installed("apps.audit"):
        audit = apps.get_model("audit", "AuditEvent")
        assert not audit.objects.filter(actor_id__in=foreign).exists()
    # The prepared reservation plus the owner's single issue.
    _assert_ledger_consistent(opening={balance.pk: (5, 0)}, operations=2)


def test_same_key_is_partitioned_per_owner_under_concurrency():
    first = _stock("race-tenant-a@standalone.test", on_hand=5)
    second_owner = _user("race-tenant-b@standalone.test")
    second_item = InventoryItem.objects.create(owner=second_owner, sku="RACE-1", name="Other")
    second_warehouse = Warehouse.objects.create(owner=second_owner, code="main", name="Main")
    second = {"owner": second_owner, "item": second_item, "warehouse": second_warehouse}
    second_balance = StockBalance.objects.create(
        owner=second_owner, warehouse=second_warehouse, item=second_item, on_hand=5
    )

    mine, theirs = _race(
        (first["owner"], _entry(first, "issue", "same-key-two-owners", 1)),
        (second_owner, _entry(second, "issue", "same-key-two-owners", 3)),
    )

    assert (mine[0], theirs[0]) == (OK, OK)
    assert mine[1]["operation_id"] != theirs[1]["operation_id"]
    assert mine[1]["balances"][0]["warehouse_id"] == str(first["warehouse"].pk)
    assert theirs[1]["balances"][0]["warehouse_id"] == str(second_warehouse.pk)
    first["balance"].refresh_from_db()
    second_balance.refresh_from_db()
    assert (first["balance"].on_hand, second_balance.on_hand) == (4, 2)
    assert InventoryOperation.objects.filter(key="same-key-two-owners").count() == 2
    opening = {first["balance"].pk: (5, 0), second_balance.pk: (5, 0)}
    _assert_ledger_consistent(opening=opening, operations=2)
