"""Namespaced best-effort cache facade. Never use it as an authorization authority."""

from hashlib import sha256

from django.core.cache import caches

MAX_TIMEOUT = 86400


def scoped_key(*, namespace: str, key: str) -> str:
    """Hash identity-bearing keys: no raw email/UUID/tenant identifiers in Redis keys."""
    if not isinstance(namespace, str) or not 1 <= len(namespace) <= 128:
        raise ValueError("Cache namespace must be 1..128 characters")
    if not isinstance(key, str) or not 1 <= len(key) <= 512:
        raise ValueError("Cache key must be 1..512 characters")
    return "v1:" + sha256((namespace + "\x00" + key).encode("utf-8")).hexdigest()


def get_cached(*, namespace: str, key: str, default=None, alias: str = "default"):
    return caches[alias].get(scoped_key(namespace=namespace, key=key), default)


def set_cached(
    *, namespace: str, key: str, value, timeout: int, alias: str = "default"
) -> None:
    if type(timeout) is not int or not 1 <= timeout <= MAX_TIMEOUT:
        raise ValueError("Cache TTL must be a positive integer up to 86400 seconds")
    caches[alias].set(scoped_key(namespace=namespace, key=key), value, timeout=timeout)


def invalidate_cached(*, namespace: str, key: str, alias: str = "default") -> None:
    caches[alias].delete(scoped_key(namespace=namespace, key=key))
