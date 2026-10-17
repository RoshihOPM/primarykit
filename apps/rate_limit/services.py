"""Redis-backed atomic account rate limiter. Never falls back on cache failure."""

import hashlib

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework.exceptions import APIException

from apps.cache.services import get_cache_service, scoped_key

# Increment and initialize first-hit expiration atomically, fixed window.
LUA = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
return {n, redis.call('PTTL', KEYS[1])}
"""


class RateLimiterUnavailable(APIException):
    status_code = 503
    default_detail = "Account protection temporarily unavailable."
    default_code = "rate_limit_unavailable"


def check_limit(*, scope: str, identity: str, max_requests: int, window_seconds: int):
    """Return (allowed, retry_seconds); non-available Redis fails closed."""
    if not getattr(settings, "REDIS_CACHE_ENABLED", False):
        raise ImproperlyConfigured("Shared rate limit requires REDIS_CACHE_ENABLED=true")
    if not isinstance(scope, str) or not 1 <= len(scope) <= 100:
        raise ValueError("Invalid scope")
    if not isinstance(identity, str) or not identity:
        raise ValueError("Invalid identity")
    if type(max_requests) is not int or max_requests < 1:
        raise ValueError("Invalid max_requests")
    if type(window_seconds) is not int or window_seconds < 1:
        raise ValueError("Invalid window_seconds")
    cache = get_cache_service()
    hashed = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    key = f"{cache.prefix}:limit:{scoped_key(namespace=scope, key=hashed)}"
    try:
        count, ttl_ms = cache.client.eval(LUA, 1, key, window_seconds * 1000)
    except Exception as exc:
        raise RateLimiterUnavailable() from exc
    allowed = int(count) <= max_requests
    wait = max(1, (int(ttl_ms) + 999) // 1000) if not allowed else None
    return allowed, wait
