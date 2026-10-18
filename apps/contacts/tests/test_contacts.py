import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User

pytestmark = pytest.mark.django_db


def client(email):
    user = User.objects.create_user(
        email=email, password="test-password", email_verified=True
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return api


def test_contacts_are_private_and_versioned():
    owner = client("contact-owner@example.test")
    stranger = client("contact-stranger@example.test")
    path = "/api/v1/contacts/"
    created = owner.post(path, {"name": "A Client", "email": "client@example.test"})
    assert created.status_code == 201, created.data
    key = created.data["id"]
    assert stranger.get(path).data["count"] == 0
    assert stranger.get(path + key + "/").status_code == 404
    assert stranger.patch(path + key + "/", {"expected_version": 0, "name": "X"}).status_code == 404
    changed = owner.patch(path + key + "/", {"expected_version": 0, "name": "B Client"})
    assert changed.status_code == 200
    assert changed.data["version"] == 1
    assert owner.patch(path + key + "/", {"expected_version": 0, "name": "Old"}).status_code == 409
    assert owner.delete(path + key + "/").status_code == 405
