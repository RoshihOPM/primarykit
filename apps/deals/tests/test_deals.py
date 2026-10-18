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


def test_deal_lifecycle_ownership_and_money_validation():
    api = client("deal-owner@example.test")
    intruder = client("deal-other@example.test")
    url = "/api/v1/deals/"
    invalid = api.post(url, {"title": "Sale", "amount_minor": -1, "currency": "usd"})
    assert invalid.status_code == 400
    created = api.post(url, {"title": "Sale", "amount_minor": 1000, "currency": "USD"})
    assert created.status_code == 201, created.data
    pk = created.data["id"]
    assert intruder.get(url + pk + "/").status_code == 404
    assert intruder.get(url).data["count"] == 0
    assert intruder.post(url + pk + "/transition/", {"expected_version": 0, "stage": "won"}).status_code == 404
    assert api.post(url + pk + "/transition/", {"expected_version": 0, "stage": "won"}).status_code == 400
    changed = api.patch(url + pk + "/", {"expected_version": 0, "amount_minor": 2000})
    assert changed.status_code == 200
    assert changed.data["version"] == 1
    assert api.patch(url + pk + "/", {"expected_version": 0, "amount_minor": 3000}).status_code == 409
    progressed = api.post(
        url + pk + "/transition/", {"expected_version": 1, "stage": "negotiation"}
    )
    assert progressed.status_code == 200
    assert progressed.data["stage"] == "negotiation"
    assert api.post(
        url + pk + "/transition/", {"expected_version": 2, "stage": "won"}
    ).status_code == 200
    assert api.delete(url + pk + "/").status_code == 405
