"""Portable redis-py CacheService for JSON values, hashes and atomic counters.

Caching is best-effort infrastructure, never authoritative for permissions, money
or inventory. Redis dependency is imported lazily: unselected clients run normally.
"""

import json
import re
from functools import lru_cache
from hashlib import sha256

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.cache.config import build_cache_config

MAX_TIMEOUT = 86400
MAX_VALUE_BYTES = 256 * 1024
FIELD = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
KINDS = frozenset({"json", "hash", "counter"})


def scoped_key(*, namespace: str, key: str) -> str:
    """Hash identity-bearing logical keys: no raw tenant IDs or emails in Redis keys."""
    if not isinstance(namespace, str) or not 1 <= len(namespace) <= 128:
        raise ValueError("Cache namespace must be 1..128 characters")
    if not isinstance(key, str) or not 1 <= len(key) <= 512:
        raise ValueError("Cache key must be 1..512 characters")
    return "v1:" + sha256((namespace + "\x00" + key).encode("utf-8")).hexdigest()


def _ttl(value: int) -> int:
    if type(value) is not int or not 1 <= value <= MAX_TIMEOUT:
        raise ValueError("Cache TTL must be a positive integer up to 86400 seconds")
    return value


def _json_encode(value) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Cache value must be JSON serializable") from exc
    if len(encoded.encode("utf-8")) > MAX_VALUE_BYTES:
        raise ValueError("Cache value exceeds 256 KiB")
    return encoded


def _field(field: str) -> str:
    if not isinstance(field, str) or not FIELD.fullmatch(field):
        raise ValueError("Hash field must be a short ASCII identifier (no private data)")
    return field


class CacheService:
    """Typed subset of redis-py. Accepts injected client for unit tests.

    Shared prefix distinguishes deployments; namespace distinguishes scopes.
    JSON/hash/counter keys cannot collide even if their logical names coincide.
    No implicit fallback to process-local cache on Redis errors.
    """

    def __init__(self, client, *, prefix: str):
        from apps.cache.config import PREFIX

        if not isinstance(prefix, str) or not PREFIX.fullmatch(prefix):
            raise ValueError("Cache prefix must uniquely identify project and environment")
        self.client = client
        self.prefix = prefix

    def _key(self, key: str, *, namespace: str, kind: str) -> str:
        if kind not in KINDS:
            raise ValueError("Unknown Redis key type")
        return f"{self.prefix}:{kind}:{scoped_key(namespace=namespace, key=key)}"

    def set_json(self, key: str, value, *, ttl: int, namespace: str = "default") -> None:
        self.client.set(
            self._key(key, namespace=namespace, kind="json"),
            _json_encode(value),
            ex=_ttl(ttl),
        )

    def get_json(self, key: str, *, namespace: str = "default", default=None):
        result = self.client.get(self._key(key, namespace=namespace, kind="json"))
        return default if result is None else json.loads(result)

    def delete(self, key: str, *, namespace: str = "default", kind: str = "json") -> int:
        """Delete a JSON, hash or counter key, never an arbitrary Redis pattern."""
        return self.client.delete(self._key(key, namespace=namespace, kind=kind))

    def hash_set(
        self, key: str, mapping: dict[str, object], *, ttl: int, namespace: str = "default"
    ) -> None:
        """HSET + EXPIRE in one atomic Redis MULTI/EXEC transaction."""
        expires = _ttl(ttl)
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("Hash mapping must be nonempty")
        values = {_field(field): _json_encode(value) for field, value in mapping.items()}
        with self.client.pipeline(transaction=True) as pipe:
            pipe.hset(self._key(key, namespace=namespace, kind="hash"), mapping=values)
            pipe.expire(self._key(key, namespace=namespace, kind="hash"), expires)
            pipe.execute()

    def hash_get(self, key: str, field: str, *, namespace: str = "default", default=None):
        value = self.client.hget(self._key(key, namespace=namespace, kind="hash"), _field(field))
        return default if value is None else json.loads(value)

    def hash_getall(self, key: str, *, namespace: str = "default") -> dict:
        value = self.client.hgetall(self._key(key, namespace=namespace, kind="hash"))
        return {field: json.loads(item) for field, item in value.items()}

    def hash_delete(self, key: str, field: str, *, namespace: str = "default") -> int:
        return self.client.hdel(self._key(key, namespace=namespace, kind="hash"), _field(field))

    def hash_increment(
        self, key: str, field: str, *, amount: int = 1, ttl: int, namespace: str = "default"
    ) -> int:
        """Atomic HINCRBY + EXPIRE. Field must contain integer JSON or be absent."""
        if type(amount) is not int:
            raise ValueError("Counter delta must be an integer")
        expires = _ttl(ttl)
        redis_key = self._key(key, namespace=namespace, kind="hash")
        with self.client.pipeline(transaction=True) as pipe:
            pipe.hincrby(redis_key, _field(field), amount)
            pipe.expire(redis_key, expires)
            result = pipe.execute()
        return int(result[0])

    def increment(
        self, key: str, *, amount: int = 1, ttl: int, namespace: str = "default"
    ) -> int:
        """Atomic INCRBY + EXPIRE on dedicated numeric keys."""
        if type(amount) is not int:
            raise ValueError("Counter delta must be an integer")
        expires = _ttl(ttl)
        redis_key = self._key(key, namespace=namespace, kind="counter")
        with self.client.pipeline(transaction=True) as pipe:
            pipe.incrby(redis_key, amount)
            pipe.expire(redis_key, expires)
            result = pipe.execute()
        return int(result[0])


@lru_cache(maxsize=8)
def _configured_service(url: str, prefix: str) -> CacheService:
    try:
        from redis import Redis
    except ImportError as exc:
        raise ImproperlyConfigured(
            "The cache module requires redis-py when enabled; install redis in this client project."
        ) from exc
    client = Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )
    return CacheService(client, prefix=prefix)


def get_cache_service() -> CacheService:
    """Explicit opt-in. Never silently serve stale in-process values on Redis failure."""
    if not getattr(settings, "REDIS_CACHE_ENABLED", False):
        raise ImproperlyConfigured("Enable REDIS_CACHE_ENABLED to use native CacheService")
    url = getattr(settings, "REDIS_CACHE_URL", "")
    prefix = getattr(settings, "REDIS_CACHE_KEY_PREFIX", "")
    # Reuse the same fail-closed URL / project-prefix rules as Django compatibility.
    build_cache_config(enabled=True, url=url, prefix=prefix)
    return _configured_service(url, prefix)


# Legacy Django Cache helpers for existing copied clients. Prefer CacheService
# for new code; these do not implement Redis hashes and remain opt-in.
def get_cached(*, namespace: str, key: str, default=None, alias: str = "default"):
    from django.core.cache import caches

    return caches[alias].get(scoped_key(namespace=namespace, key=key), default)


def set_cached(*, namespace: str, key: str, value, timeout: int, alias: str = "default") -> None:
    from django.core.cache import caches

    caches[alias].set(scoped_key(namespace=namespace, key=key), value, timeout=_ttl(timeout))


def invalidate_cached(*, namespace: str, key: str, alias: str = "default") -> None:
    from django.core.cache import caches

    caches[alias].delete(scoped_key(namespace=namespace, key=key))
