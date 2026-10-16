"""Live Redis integration (requires explicit CI opt-in and redis-py installation)."""

import os
import uuid

import pytest
from django.core.cache import caches
from django.test import override_settings

from apps.cache.config import build_cache_config
from apps.cache.services import CacheService, get_cached, get_cache_service, invalidate_cached, set_cached

pytestmark = pytest.mark.skipif(
    os.environ.get("PRIMARYKIT_INFRA_INTEGRATION") != "1",
    reason="Only run against explicitly provisioned Redis",
)


def test_native_redis_service_json_hashes_counter_and_ttl():
    redis = pytest.importorskip("redis")
    client = redis.Redis.from_url(os.environ["REDIS_CACHE_URL"], decode_responses=True)
    unique_prefix = "primarykit-ci-" + uuid.uuid4().hex[:16]
    cache = CacheService(client, prefix=unique_prefix)
    cache.set_json("item", {"price": 150, "visible": True}, namespace="tenant-a", ttl=30)
    assert cache.get_json("item", namespace="tenant-a") == {"price": 150, "visible": True}
    assert cache.get_json("item", namespace="tenant-b") is None
    cache.hash_set("item", {"price": 150, "brand": "Hyundai"}, namespace="tenant-a", ttl=30)
    assert cache.hash_get("item", "brand", namespace="tenant-a") == "Hyundai"
    assert cache.hash_increment("item", "views", namespace="tenant-a", ttl=40) == 1
    assert cache.hash_increment("item", "views", amount=4, namespace="tenant-a", ttl=40) == 5
    assert cache.hash_getall("item", namespace="tenant-a")["views"] == 5
    assert cache.increment("item", namespace="tenant-a", ttl=30) == 1
    assert cache.increment("item", amount=2, namespace="tenant-a", ttl=30) == 3
    assert cache.get_json("item", namespace="tenant-a")["price"] == 150
    json_key = cache._key("item", namespace="tenant-a", kind="json")
    hash_key = cache._key("item", namespace="tenant-a", kind="hash")
    counter_key = cache._key("item", namespace="tenant-a", kind="counter")
    assert 0 < client.ttl(json_key) <= 30
    assert 0 < client.ttl(hash_key) <= 40
    assert 0 < client.ttl(counter_key) <= 30
    assert cache.hash_delete("item", "brand", namespace="tenant-a") == 1
    for kind in ("json", "hash", "counter"):
        cache.delete("item", namespace="tenant-a", kind=kind)
    assert not client.exists(json_key, hash_key, counter_key)


def test_factory_is_lazy_and_configured_per_client():
    pytest.importorskip("redis")
    with override_settings(
        REDIS_CACHE_ENABLED=True,
        REDIS_CACHE_URL=os.environ["REDIS_CACHE_URL"],
        REDIS_CACHE_KEY_PREFIX="primarykit-ci-native",
    ):
        cache = get_cache_service()
        cache.set_json("factory-test", {"ok": True}, ttl=20)
        assert get_cache_service().get_json("factory-test") == {"ok": True}
        cache.delete("factory-test")


def test_legacy_django_cache_adapter_is_still_optional():
    pytest.importorskip("redis")
    configuration = build_cache_config(
        enabled=True,
        url=os.environ["REDIS_CACHE_URL"],
        prefix="primarykit-ci-django",
        timeout=30,
    )
    with override_settings(CACHES={"default": configuration}):
        caches["default"].set("healthcheck", "ok", timeout=20)
        assert caches["default"].get("healthcheck") == "ok"
        set_cached(namespace="client-a", key="same", value="A", timeout=30)
        assert get_cached(namespace="client-a", key="same") == "A"
        assert get_cached(namespace="client-b", key="same") is None
        invalidate_cached(namespace="client-a", key="same")
        assert get_cached(namespace="client-a", key="same") is None
        caches["default"].delete("healthcheck")
