from django.urls import reverse


def test_liveness(client):
    response = client.get(reverse("health-live"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_liveness_is_get_only(client):
    assert client.post(reverse("health-live")).status_code == 405


def test_readiness(client, db):
    response = client.get(reverse("health-ready"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
