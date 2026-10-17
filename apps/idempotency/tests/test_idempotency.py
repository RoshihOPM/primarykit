from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from time import sleep

import pytest
from django.db import NotSupportedError, close_old_connections, connection, connections
from django.utils import timezone

from apps.idempotency.models import CommandReceipt
from apps.idempotency.services import IdempotencyConflict, execute_once, fingerprint

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("scope,key", [("", "key"), ("a", ""), ("a b", "key"), ("a", "bad key")])
def test_rejects_invalid_scope_or_key(scope, key):
    with pytest.raises(ValueError):
        execute_once(scope=scope, key=key, request={"one": 1}, operation=lambda: None)


def test_deterministic_fingerprint_and_limits():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
    with pytest.raises(ValueError):
        fingerprint({"bad": float("nan")})
    with pytest.raises(ValueError):
        fingerprint({"too_big": "x" * 66000})


def test_sqlite_does_not_claim_concurrent_safety():
    if connection.vendor == "postgresql":
        pytest.skip("PostgreSQL test configured below")
    with pytest.raises(NotSupportedError):
        execute_once(scope="actor:1:checkout", key="req-1", request={}, operation=lambda: {})


def test_postgresql_replay_conflict_and_rollback():
    if connection.vendor != "postgresql":
        pytest.skip("Only PostgreSQL provides required locking")
    called = []
    scope = "users:actor-1:orders.create"

    def create():
        called.append(1)
        return {"order_id": 12}

    result, replay = execute_once(scope=scope, key="req1", request={"price": 99}, operation=create)
    assert (result, replay) == ({"order_id": 12}, False)
    result, replay = execute_once(scope=scope, key="req1", request={"price": 99}, operation=create)
    assert (result, replay) == ({"order_id": 12}, True)
    assert len(called) == 1
    with pytest.raises(IdempotencyConflict):
        execute_once(scope=scope, key="req1", request={"price": 100}, operation=create)
    with pytest.raises(RuntimeError):
        execute_once(
            scope=scope,
            key="req2",
            request={},
            operation=lambda: (_ for _ in ()).throw(RuntimeError()),
        )
    assert not CommandReceipt.objects.filter(scope=scope, key="req2").exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_key_runs_operation_once():
    if connection.vendor != "postgresql":
        pytest.skip("Concurrency requires PostgreSQL")
    barrier = Barrier(2)
    lock = Lock()
    executions = []
    key = "race"
    scope = "users:actor-1:orders.create"

    def worker(_index):
        close_old_connections()
        try:
            barrier.wait(timeout=15)

            def operation():
                with lock:
                    executions.append(timezone.now().isoformat())
                sleep(0.1)
                return {"ok": True}

            return execute_once(scope=scope, key=key, request={"payload": 1}, operation=operation)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))
    assert len(executions) == 1
    assert sorted(replayed for _result, replayed in results) == [False, True]
    assert CommandReceipt.objects.filter(scope=scope, key=key).count() == 1
