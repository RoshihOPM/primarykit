"""CacheService behaviour without any external Redis dependency."""

import json

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.cache.services import CacheService, get_cache_service, scoped_key


class FakePipeline:
    def __init__(self, client):
        self.client = client
        self.commands = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def hset(self, key, mapping):
        self.commands.append(("hset", (key,), {"mapping": mapping}))
        return self

    def hincrby(self, key, field, amount):
        self.commands.append(("hincrby", (key, field, amount), {}))
        return self

    def incrby(self, key, amount):
        self.commands.append(("incrby", (key, amount), {}))
        return self

    def expire(self, key, seconds):
        self.commands.append(("expire", (key, seconds), {}))
        return self

    def execute(self):
        results = []
        for name, args, kwargs in self.commands:
            results.append(getattr(self.client, name)(*args, **kwargs))
        return results


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    def set(self, key, value, ex):
        self.values[key] = value
        self.ttls[key] = ex

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        return int(self.values.pop(key, None) is not None)

    def hset(self, key, mapping):
        value = self.values.setdefault(key, {})
        value.update(mapping)
        return len(mapping)

    def hget(self, key, field):
        return self.values.get(key, {}).get(field)

    def hgetall(self, key):
        return dict(self.values.get(key, {}))

    def hdel(self, key, field):
        return int(self.values.get(key, {}).pop(field, None) is not None)

    def hincrby(self, key, field, amount):
        value = self.values.setdefault(key, {})
        current = int(value.get(field, "0")) + amount
        value[field] = str(current)
        return current

    def incrby(self, key, amount):
        current = int(self.values.get(key, "0")) + amount
        self.values[key] = str(current)
        return current

    def expire(self, key, seconds):
        self.ttls[key] = seconds
        return True

    def pipeline(self, transaction=True):
        assert transaction is True
        return FakePipeline(self)


def test_json_values_are_typed_and_tenant_isolated():
    fake = FakeRedis()
    cache = CacheService(fake, prefix="test-env")
    cache.set_json("listing:100", {"price": 5, "available": False}, namespace="tenant:A", ttl=45)
    assert cache.get_json("listing:100", namespace="tenant:A") == {
        "price": 5,
        "available": False,
    }
    assert cache.get_json("listing:100", namespace="tenant:B") is None
    assert cache.get_json("missing", default="fallback") == "fallback"
    assert cache.delete("listing:100", namespace="tenant:A") == 1
    assert cache.get_json("listing:100", namespace="tenant:A") is None
    actual_key = next(iter(fake.ttls))
    assert "tenant:A" not in actual_key and "listing:100" not in actual_key
    assert fake.ttls[actual_key] == 45
    assert actual_key.startswith("test-env:json:v1:")
    assert scoped_key(namespace="tenant:A", key="x") != scoped_key(
        namespace="tenant:B", key="x"
    )


def test_hash_fields_json_null_and_native_integer_increment():
    fake = FakeRedis()
    cache = CacheService(fake, prefix="test-env")
    cache.hash_set("listing:1", {"price": 100, "brand": "Kia", "promoted": True}, ttl=120)
    assert cache.hash_get("listing:1", "brand") == "Kia"
    assert cache.hash_get("listing:1", "promoted") is True
    assert cache.hash_increment("listing:1", "views", ttl=120) == 1
    assert cache.hash_increment("listing:1", "views", amount=3, ttl=60) == 4
    assert cache.hash_get("listing:1", "views") == 4
    assert cache.hash_getall("listing:1") == {
        "price": 100,
        "brand": "Kia",
        "promoted": True,
        "views": 4,
    }
    assert cache.hash_delete("listing:1", "brand") == 1
    hash_key = next(key for key in fake.values if ":hash:" in key)
    assert fake.ttls[hash_key] == 60
    assert cache.delete("listing:1", kind="hash") == 1


def test_numeric_counter_and_json_keys_do_not_collide():
    fake = FakeRedis()
    cache = CacheService(fake, prefix="test-env")
    cache.set_json("views", {"count": 10}, ttl=60)
    assert cache.increment("views", ttl=30) == 1
    assert cache.increment("views", amount=5, ttl=15) == 6
    assert cache.get_json("views") == {"count": 10}
    counter = next(key for key in fake.values if ":counter:" in key)
    assert fake.ttls[counter] == 15
    assert cache.delete("views", kind="counter") == 1


@pytest.mark.parametrize(
    "bad_value",
    [float("nan"), {"bad": object()}, {1, 2}, "x" * (300 * 1024)],
)
def test_rejects_unsafe_or_oversized_json(bad_value):
    cache = CacheService(FakeRedis(), prefix="test-env")
    with pytest.raises(ValueError):
        cache.set_json("key", bad_value, ttl=20)


def test_invalid_ttl_field_namespace_and_counters_fail_without_writes():
    fake = FakeRedis()
    cache = CacheService(fake, prefix="test-env")
    with pytest.raises(ValueError):
        cache.set_json("key", 1, ttl=True)
    with pytest.raises(ValueError):
        cache.hash_set("key", {"email@example.com": 1}, ttl=20)
    with pytest.raises(ValueError):
        cache.hash_set("key", {}, ttl=20)
    with pytest.raises(ValueError):
        cache.hash_set("key", {"counter": 1}, ttl=0)
    with pytest.raises(ValueError):
        cache.hash_increment("key", "hits", amount=True, ttl=20)
    with pytest.raises(ValueError):
        cache.increment("key", amount=1.5, ttl=20)
    with pytest.raises(ValueError):
        cache.get_json("key", namespace="")
    with pytest.raises(ValueError):
        cache.delete("key", kind="danger")
    assert not fake.values


def test_missing_opt_in_is_explicit_error():
    with override_settings(REDIS_CACHE_ENABLED=False):
        with pytest.raises(ImproperlyConfigured, match="REDIS_CACHE_ENABLED"):
            get_cache_service()


def test_invalid_settings_fail_before_redis_import():
    with override_settings(
        REDIS_CACHE_ENABLED=True,
        REDIS_CACHE_URL="http://bad",
        REDIS_CACHE_KEY_PREFIX="testing",
    ):
        with pytest.raises(ImproperlyConfigured, match="redis"):
            get_cache_service()


def test_explicit_json_null_is_not_a_cache_miss():
    cache = CacheService(FakeRedis(), prefix="test-env")
    cache.set_json("nullable", None, ttl=20)
    assert cache.get_json("nullable", default="missing") is None
    assert json.loads("null") is None
