"""Cross-worker isolation checks require PostgreSQL row locking."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, connections

from apps.kanban.models import Board, Card, CardMove, Column
from apps.kanban.services import StaleCard, move_card
from apps.users.models import User


@pytest.mark.django_db(transaction=True)
def test_postgresql_two_simultaneous_moves_commit_once():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL required for select_for_update")
    owner = User.objects.create_user(email="race-kanban@example.test", password="test-password")
    board = Board.objects.create(owner=owner, name="Race")
    first = Column.objects.create(board=board, name="New")
    second = Column.objects.create(board=board, name="Done")
    card = Card.objects.create(board=board, column=first, title="Race")
    barrier = Barrier(2)

    def worker(_index):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            try:
                move_card(
                    actor=owner, card_id=card.pk,
                    target_column_id=second.pk, expected_version=0,
                )
            except StaleCard:
                return "stale"
            return "moved"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(worker, range(2)))
    assert sorted(outcomes) == ["moved", "stale"]
    card.refresh_from_db()
    assert card.version == 1
    assert card.column_id == second.pk
    assert CardMove.objects.filter(card=card).count() == 1
