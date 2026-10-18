import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User

pytestmark = pytest.mark.django_db


def client(email):
    user = User.objects.create_user(email=email, password="strongpass", email_verified=True)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return api


def test_lead_privacy_and_transitions():
    api = client("leads-owner@example.test")
    other = client("leads-other@example.test")
    url = "/api/v1/leads/"
    created = api.post(url, {"title": "Sales lead", "contact_name": "Customer"})
    assert created.status_code == 201, created.data
    pk = created.data["id"]
    assert other.get(url).data["count"] == 0
    assert other.get(url + pk + "/").status_code == 404
    assert (
        other.post(url + pk + "/transition/", {"status": "won", "expected_version": 0}).status_code
        == 404
    )
    assert (
        api.post(url + pk + "/transition/", {"status": "won", "expected_version": 0}).status_code
        == 400
    )
    qualified = api.post(url + pk + "/transition/", {"status": "qualified", "expected_version": 0})
    assert qualified.status_code == 200
    assert qualified.data["version"] == 1
    assert (
        api.post(url + pk + "/transition/", {"status": "won", "expected_version": 0}).status_code
        == 409
    )
    assert (
        api.post(url + pk + "/transition/", {"status": "won", "expected_version": 1}).status_code
        == 200
    )
    assert api.patch(url + pk + "/", {"status": "new", "version": 0}).status_code == 400
    edited = api.patch(url + pk + "/", {"expected_version": 2, "notes": "Call back"})
    assert edited.status_code == 200
    assert edited.data["version"] == 3
    assert api.patch(url + pk + "/", {"expected_version": 2, "notes": "Lost update"}).status_code == 409
    assert other.patch(url + pk + "/", {"expected_version": 3, "notes": "Intrusion"}).status_code == 404
