import pytest
from rest_framework.exceptions import NotFound

from apps.kanban.models import Board, Card, CardMove, Column
from apps.kanban.services import create_card, edit_card, move_card
from apps.users.models import User

pytestmark = pytest.mark.django_db


def test_dense_reorder_and_cross_column_move():
    owner = User.objects.create_user(email="reorder-owner@example.test", password="strong-pass")
    board = Board.objects.create(owner=owner, name="Operations")
    todo = Column.objects.create(board=board, name="Todo")
    done = Column.objects.create(board=board, name="Done")
    cards = [
        create_card(actor=owner, board_id=board.pk, column_id=todo.pk, title=f"Task {i}")
        for i in range(3)
    ]
    assert [card.position for card in cards] == [0, 1, 2]

    moved = move_card(
        actor=owner,
        card_id=cards[2].pk,
        target_column_id=todo.pk,
        expected_version=0,
        position=0,
    )
    assert moved.position == 0
    assert list(Card.objects.filter(column=todo).values_list("position", flat=True)) == [0, 1, 2]

    moved = move_card(
        actor=owner,
        card_id=cards[2].pk,
        target_column_id=done.pk,
        expected_version=moved.version,
        position=0,
    )
    assert moved.column_id == done.pk
    assert list(Card.objects.filter(column=todo).values_list("position", flat=True)) == [0, 1]
    assert CardMove.objects.filter(card=moved).count() == 1

    edited = edit_card(
        actor=owner,
        card_id=moved.pk,
        expected_version=moved.version,
        changes={"title": "Reviewed"},
    )
    assert edited.title == "Reviewed"
    assert edited.version == moved.version + 1


def test_board_isolation_does_not_leak_existence():
    owner = User.objects.create_user(email="board-owner@example.test", password="strong-pass")
    stranger = User.objects.create_user(email="board-other@example.test", password="strong-pass")
    board = Board.objects.create(owner=owner, name="Private")
    col = Column.objects.create(board=board, name="Inbox")
    card = create_card(actor=owner, board_id=board.pk, column_id=col.pk, title="Secret")
    with pytest.raises(NotFound):
        edit_card(actor=stranger, card_id=card.pk, expected_version=0, changes={"title": "Stolen"})
