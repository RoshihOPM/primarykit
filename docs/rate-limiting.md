# Distributed account rate limiting via Redis

Opt in with `--apps rate_limit`: generator includes the **cache** module automatically. This app does not add DB migrations or a public endpoint. By default, existing DRF `ScopedRateThrottle` still handles local/dev traffic. To use a shared rate limiter in a deployed client, install redis-py (see [Redis Cache](redis-cache.md)), configure a private Redis, and set both `REDIS_CACHE_ENABLED=true` and `SHARED_ACCOUNT_THROTTLE_ENABLED=true`.

`AccountRateThrottle` then counts authenticated users or anonymous client IP identities atomically across all Gunicorn workers using Redis `INCR` and `PEXPIRE` in a single Lua execution. One window begins on the first attempt, expires after its configured duration, and cannot be bypassed by repeated invalid logins. Counters are scoped by endpoint (`account_login`, `account_registration`, `account_password`, etc.), environment, and hashed identity.

Redis failures are **fail-closed** for authentication endpoints (503); clients should retry later. There is no transparent switch to per-process memory, which would undermine global limits. Keep Redis private and monitored. If you require strict edge-level DDoS mitigation, configure Nginx/CDN rules **in addition** to the application limiter.

The server derives anonymous IP from `REMOTE_ADDR`, **not arbitrary X-Forwarded-For**. If your trusted reverse proxy sits in front of Django, configure Nginx `real_ip` only for **known upstream proxy IP ranges**; otherwise all users may appear as the proxy IP or a spoofed value.

The algorithm uses fixed windows, not a perfectly smooth sliding limiter. DRF's existing rates configure each window. Redis cache is not an authorization authority or permanent counter ledger. For sessions, money and finance, use PostgreSQL.

Start project:

```bash
uv run python scripts/new_project.py ../public-api --name public-api --apps rate_limit
cd ../public-api
uv add 'redis>=8,<9'
cp .env.example .env
# REDIS_CACHE_ENABLED=true
# SHARED_ACCOUNT_THROTTLE_ENABLED=true
# REDIS_CACHE_KEY_PREFIX=public-api-prod
docker compose -f compose.yaml -f compose.redis.yaml up -d
```

Production Redis must use private networking, authentication and preferably TLS. No PrimaryKit runtime dependency.
