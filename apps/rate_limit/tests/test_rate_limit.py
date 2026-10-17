"""Atomic limiter unit tests without live Redis."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.rate_limit.services import RateLimiterUnavailable, check_limit


class FakeRedis:
    def __init__(self):
        self.requests = []

    def eval(self, script, count, key, milliseconds):
        self.requests.append((script, count, key, milliseconds))
        return len(self.requests), milliseconds


class FakeService:
    prefix = "my-app-prod"

    def __init__(self, client):
        self.client = client


@override_settings(REDIS_CACHE_ENABLED=True)
def test_atomic_counter_namespaces_and_retries(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr("apps.rate_limit.services.get_cache_service", lambda: FakeService(client))
    assert check_limit(scope="login", identity="ip:10.1.1.1", max_requests=2, window_seconds=60) == (
        True,
        None,
    )
    assert check_limit(scope="login", identity="ip:10.1.1.1", max_requests=2, window_seconds=60) == (
        True,
        None,
    )
    assert check_limit(scope="login", identity="ip:10.1.1.1", max_requests=2, window_seconds=60) == (
        False,
        60,
    )
    assert "10.1.1.1" not in client.requests[0][2]
    assert "PEXPIRE" in client.requests[0][0]
    assert client.requests[0][3] == 60000


@override_settings(REDIS_CACHE_ENABLED=False)
def test_no_silent_throttle_bypass():
    with pytest.raises(ImproperlyConfigured, match="REDIS_CACHE_ENABLED"):
        check_limit(scope="login", identity="ip:1.1.1.1", max_requests=1, window_seconds=60)


@override_settings(REDIS_CACHE_ENABLED=True)
def test_network_error_fail_closed(monkeypatch):
    class Broken:
        def eval(self, *args):
            raise ConnectionError("do not leak secrets")

    monkeypatch.setattr("apps.rate_limit.services.get_cache_service",
                        lambda: FakeService(Broken()))
    with pytest.raises(RateLimiterUnavailable, match="temporarily unavailable"):
        check_limit(scope="login", identity="ip:1.1.1.1", max_requests=1, window_seconds=60)


@override_settings(SHARED_ACCOUNT_THROTTLE_ENABLED=True)
def test_account_endpoint_delegates_to_shared_redis(monkeypatch):
    from types import SimpleNamespace

    from django.contrib.auth.models import AnonymousUser

    from apps.users.throttles import AccountRateThrottle

    calls = []

    def record(**kwargs):
        calls.append(kwargs)
        return False, 11

    monkeypatch.setattr("apps.rate_limit.services.check_limit", record)
    request = SimpleNamespace(META={"REMOTE_ADDR": "192.0.2.42"}, user=AnonymousUser())
    view = SimpleNamespace(throttle_scope="account_login")
    throttle = AccountRateThrottle()
    assert throttle.allow_request(request, view) is False
    assert throttle.wait() == 11
    assert calls[0]["identity"] == "ip:192.0.2.42"
    assert calls[0]["window_seconds"] == 60
