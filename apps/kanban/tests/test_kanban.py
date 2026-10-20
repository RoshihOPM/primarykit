import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import NotFound, ValidationError

from apps.kanban.manifest import MODULE
from apps.kanban.models import Board, Card, CardMove, Column
from apps.kanban.services import move_card


def test_manifest():
    assert MODULE.name == "kanban"
    assert MODULE.requires == ("users",)


@pytest.mark.django_db
def test_move_card_enforces_owner_board_and_version():
    user_model = get_user_model()
    owner = user_model.objects.create_user(
        email="kanban_owner@example.com", password="test-password"
    )
    other = user_model.objects.create_user(
        email="kanban_other@example.com", password="test-password"
    )
    board = Board.objects.create(owner=owner, name="Work")
    a = Column.objects.create(board=board, name="Todo")
    b = Column.objects.create(board=board, name="Done")
    foreign = Column.objects.create(
        board=Board.objects.create(owner=other, name="Other"), name="No"
    )
    card = Card.objects.create(board=board, column=a, title="Task")

    with pytest.raises(NotFound):
        move_card(actor=other, card_id=card.pk, target_column_id=b.pk, expected_version=0)
    with pytest.raises(ValidationError):
        move_card(actor=owner, card_id=card.pk, target_column_id=foreign.pk, expected_version=0)
    with pytest.raises(ValidationError):
        move_card(actor=owner, card_id=card.pk, target_column_id=b.pk, expected_version=1)
    assert CardMove.objects.count() == 0

    moved = move_card(actor=owner, card_id=card.pk, target_column_id=b.pk, expected_version=0)
    assert moved.column_id == b.pk
    assert moved.version == 1
    assert CardMove.objects.get(card=card).actor_id == owner.pk

    repeated = move_card(actor=owner, card_id=card.pk, target_column_id=b.pk, expected_version=1)
    assert repeated.version == 1
    assert CardMove.objects.count() == 1
