"""Build Django cache settings without connecting to Redis at import time."""

import re
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

PREFIX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def build_cache_config(*, enabled: bool, url: str, prefix: str, timeout: int = 300, backend: str = "django") -> dict:
    """Redis must be explicit; local backend is process-local and non-shared."""
    if not enabled:
        return {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    if not isinstance(url, str) or not url:
        raise ImproperlyConfigured("REDIS_CACHE_URL is required when REDIS_CACHE_ENABLED=true")
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme in {"redis", "rediss"}
            and bool(parsed.hostname)
            and parsed.port not in {0}
            and not parsed.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise ImproperlyConfigured("REDIS_CACHE_URL must be a valid redis:// or rediss:// URL")
    if not isinstance(prefix, str) or not PREFIX.fullmatch(prefix):
        raise ImproperlyConfigured(
            "REDIS_CACHE_KEY_PREFIX must be a non-empty unique project identifier"
        )
    if type(timeout) is not int or not 1 <= timeout <= 86400:
        raise ImproperlyConfigured("REDIS_CACHE_TIMEOUT must be between 1 and 86400 seconds")
    if backend == "django":
        return {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": url,
            "KEY_PREFIX": prefix,
            "TIMEOUT": timeout,
            "OPTIONS": {"socket_connect_timeout": 2, "socket_timeout": 2},
        }
    if backend == "django-redis":
        return {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": url,
            "KEY_PREFIX": prefix,
            "TIMEOUT": timeout,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "SOCKET_CONNECT_TIMEOUT": 2,
                "SOCKET_TIMEOUT": 2,
            },
        }
    raise ImproperlyConfigured("REDIS_CACHE_DJANGO_BACKEND must be none, django or django-redis")
