"""Cache functionality is testable without a Redis service."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.cache.config import build_cache_config
from apps.cache.services import get_cached, invalidate_cached, scoped_key, set_cached


def test_local_backend_requires_no_redis_dependency():
    assert "locmem" in build_cache_config(enabled=False, url="", prefix="")["BACKEND"]


@pytest.mark.parametrize(
    ("url", "prefix", "timeout"),
    [
        ("", "project-a", 60),
        ("http://localhost:6379/0", "project-a", 60),
        ("redis:///", "project-a", 60),
        ("redis://localhost:6379/0", "", 60),
        ("redis://localhost:6379/0", "invalid:prefix", 60),
        ("redis://localhost:6379/0", "project-a", 0),
        ("redis://localhost:6379/0", "project-a", 86401),
    ],
)
def test_invalid_cache_configuration_fails_closed(url, prefix, timeout):
    with pytest.raises(ImproperlyConfigured):
        build_cache_config(enabled=True, url=url, prefix=prefix, timeout=timeout)


def test_redis_configuration_is_lazy_and_project_scoped():
    cfg = build_cache_config(
        enabled=True, url="rediss://cache.example.test:6380/3", prefix="my-backend"
    )
    assert cfg["BACKEND"] == "django.core.cache.backends.redis.RedisCache"
    assert cfg["KEY_PREFIX"] == "my-backend"
    assert cfg["LOCATION"].startswith("rediss://")


def test_optional_django_redis_backend_configuration():
    config = build_cache_config(
        enabled=True,
        url="rediss://redis.example.test:6380/0",
        prefix="client-prod",
        timeout=60,
        backend="django-redis",
    )
    assert config["BACKEND"] == "django_redis.cache.RedisCache"
    assert config["OPTIONS"]["CLIENT_CLASS"] == "django_redis.client.DefaultClient"
    with pytest.raises(ImproperlyConfigured, match="BACKEND"):
        build_cache_config(
            enabled=True,
            url="redis://localhost:6379/0",
            prefix="client",
            backend="unsupported",
        )


def test_namespaced_cache_uses_hashed_keys_and_explicit_ttl():
    assert "alice" not in scoped_key(namespace="tenant:alice", key="user@example.test")
    assert scoped_key(namespace="tenant:a", key="1") != scoped_key(namespace="tenant:b", key="1")
    with override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    ):
        set_cached(namespace="tenant:a", key="same", value={"value": 1}, timeout=30)
        assert get_cached(namespace="tenant:a", key="same") == {"value": 1}
        assert get_cached(namespace="tenant:b", key="same") is None
        invalidate_cached(namespace="tenant:a", key="same")
        assert get_cached(namespace="tenant:a", key="same") is None
        with pytest.raises(ValueError, match="TTL"):
            set_cached(namespace="tenant:a", key="same", value=1, timeout=0)
