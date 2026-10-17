import io
import urllib.error

import pytest

from apps.http_integrations import services
from apps.http_integrations.services import ProviderClient, ProviderTransportError


class FakeResponse:
    def __init__(self, status, body=b"{}"):
        self.status = status
        self.stream = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size):
        return self.stream.read(size)


def client(**settings):
    return ProviderClient(
        base_url="https://api.vendor.example/v1",
        allowed_hosts=("api.vendor.example",),
        **settings,
    )


@pytest.mark.parametrize(
    "origin",
    [
        "http://api.vendor.example",
        "https://127.0.0.1",
        "https://localhost",
        "https://evil.example",
        "https://api.vendor.example:8000",
    ],
)
def test_only_explicit_trusted_https_origins(origin):
    with pytest.raises(ValueError):
        ProviderClient(base_url=origin, allowed_hosts=("api.vendor.example",))


@pytest.mark.parametrize(
    "path", ["https://evil.example/x", "//evil.example", "/safe#secret", "/../admin"]
)
def test_cannot_override_provider_origin_or_path(path):
    with pytest.raises(ValueError):
        client().request("GET", path)


def test_retries_only_safe_methods_or_idempotent_writes(monkeypatch):
    calls = []

    def send(request, _timeout):
        calls.append(request)
        return FakeResponse(503 if len(calls) == 1 else 200)

    monkeypatch.setattr(services, "_open", send)
    monkeypatch.setattr(services.time, "sleep", lambda _wait: None)
    response = client(retries=2).request("GET", "/resource")
    assert response.status == 200 and len(calls) == 2

    calls.clear()
    response = client(retries=2).request("POST", "/items", payload={"quantity": 1})
    assert response.status == 503 and len(calls) == 1

    calls.clear()
    response = client(retries=2).request(
        "POST", "/items", payload={"quantity": 1}, idempotency_key="signed-safe-1"
    )
    assert response.status == 200 and len(calls) == 2
    assert calls[-1].get_header("Idempotency-key") == "signed-safe-1"


def test_bounded_responses_and_sanitized_transport_error(monkeypatch):
    monkeypatch.setattr(services, "_open", lambda *_args: FakeResponse(200, b"x" * 8))
    with pytest.raises(ProviderTransportError):
        client(max_response_bytes=4).request("GET", "/ok?token=private")

    def fail(*_args):
        raise urllib.error.URLError("https://private-url/?token=secret")

    monkeypatch.setattr(services, "_open", fail)
    with pytest.raises(ProviderTransportError, match="Provider request failed") as error:
        client(retries=0).request("GET", "/ok")
    assert "secret" not in str(error.value)


def test_no_redirect_to_other_origins():
    assert (
        services._NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example")
        is None
    )
