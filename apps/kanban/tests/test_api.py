import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User

pytestmark = pytest.mark.django_db


def test_kanban_api_enforces_owner_and_move():
    owner = User.objects.create_user(
        email="owner-kanban@example.test", password="strongpass", email_verified=True
    )
    other = User.objects.create_user(
        email="other-kanban@example.test", password="strongpass", email_verified=True
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(owner).access_token}")
    other_api = APIClient()
    other_api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(other).access_token}")
    root = "/api/v1/kanban/"
    board = api.post(root + "boards/", {"name": "Sales"}).data["id"]
    col1 = api.post(root + "columns/", {"board": board, "name": "New"}).data["id"]
    col2 = api.post(root + "columns/", {"board": board, "name": "Done"}).data["id"]
    created = api.post(root + "cards/", {"board": board, "column": col1, "title": "Lead"})
    assert created.status_code == 201, created.data
    card = created.data["id"]
    assert other_api.get(root + "boards/").data["count"] == 0
    assert other_api.get(root + "cards/" + card + "/").status_code == 404
    assert (
        other_api.post(root + "cards/", {"board": board, "column": col1, "title": "No"}).status_code
        == 404
    )
    assert api.patch(root + "cards/" + card + "/", {"column": col2}).status_code == 400
    moved = api.post(
        root + "cards/" + card + "/move/", {"target_column_id": col2, "expected_version": 0}
    )
    assert moved.status_code == 200, moved.data
    assert str(moved.data["column"]) == col2
    assert (
        api.post(
            root + "cards/" + card + "/move/", {"target_column_id": col1, "expected_version": 0}
        ).status_code
        == 409
    )
    assert APIClient().get(root + "boards/").status_code in (401, 403)
