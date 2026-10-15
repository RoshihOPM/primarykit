"""Prove invariant under independent PostgreSQL writers (not SQLite simulation)."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections, connection
from rest_framework.exceptions import ValidationError

from apps.catalog.models import CatalogItem, Category
from apps.inventory.models import StockBalance, Warehouse
from apps.inventory.services import execute_stock_operation
from apps.users.models import User


@pytest.mark.django_db(transaction=True)
def test_two_writers_cannot_overdraw_the_same_stock():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row-lock test requires PostgreSQL")
    category = Category.objects.create(slug="supplies", name="Supplies")
    item = CatalogItem.objects.create(category=category, sku="SKU-1", name="Supply")
    warehouse = Warehouse.objects.create(code="warehouse", name="Warehouse")
    actor = User.objects.create_user(
        email="concurrent-admin@example.test",
        password="Concurrent-test-password-111",
        email_verified=True,
        is_staff=True,
        is_superuser=True,
    )
    StockBalance.objects.create(warehouse=warehouse, item=item, on_hand=5)
    barrier = Barrier(2)

    def worker(number):
        close_old_connections()
        barrier.wait(timeout=10)
        try:
            execute_stock_operation(
                actor=actor,
                data={
                    "kind": "issue",
                    "idempotency_key": f"concurrent-issue-{number}",
                    "warehouse": warehouse,
                    "item": item,
                    "quantity": 4,
                },
            )
            return "success"
        except ValidationError:
            return "rejected"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, (1, 2)))
    assert sorted(results) == ["rejected", "success"]
    balance = StockBalance.objects.get(warehouse=warehouse, item=item)
    assert balance.on_hand == 1
    assert balance.reserved == 0
