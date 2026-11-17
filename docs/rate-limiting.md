# Distributed account rate limiting via Redis

Opt in with `--apps rate_limit`: generator includes the **cache** module automatically. This app does not add DB migrations or a public endpoint. By default, existing DRF `ScopedRateThrottle` still handles local/dev traffic. To use a shared rate limiter in a deployed client, install redis-py (see [Redis Cache](redis-cache.md)), configure a private Redis, and set both `REDIS_CACHE_ENABLED=true` and `SHARED_ACCOUNT_THROTTLE_ENABLED=true`.

`AccountRateThrottle` then counts authenticated users or anonymous client IP identities atomically across all Gunicorn workers using Redis `INCR` and `PEXPIRE` in a single Lua execution. One window begins on the first attempt, expires after its configured duration, and cannot be bypassed by repeated invalid logins. Counters are scoped by endpoint (`account_login`, `account_registration`, `account_password`, etc.), environment, and hashed identity.

Redis failures are **fail-closed** for authentication endpoints (503); clients should retry later. There is no transparent switch to per-process memory, which would undermine global limits. Keep Redis private and monitored. If you require strict edge-level DDoS mitigation, configure Nginx/CDN rules **in addition** to the application limiter.

## Anonymous client identity: `DJANGO_NUM_PROXIES`

Both modes (local DRF cache and shared Redis) derive the anonymous identity through one helper, `apps.users.throttles.client_ident`, driven by one deployment-owned setting: `DJANGO_NUM_PROXIES`, exposed to DRF as `REST_FRAMEWORK["NUM_PROXIES"]`. It is the number of **trusted** reverse-proxy hops between the internet and Django that overwrite or append `X-Forwarded-For`.

| Value | Identity | Use when |
| --- | --- | --- |
| `0` (default) | `REMOTE_ADDR`; `X-Forwarded-For` is ignored entirely | Django is reached directly, or the proxy is unknown |
| `1` | right-most `X-Forwarded-For` address | the shipped `deploy/nginx` example (one proxy) |
| `N` | N-th address from the right | N chained trusted hops, e.g. CDN/load balancer → nginx is `2` |

Rules an operator must know:

- **The default is safe against spoofing but coarse behind a proxy.** With `0` behind nginx every anonymous caller has the proxy's `REMOTE_ADDR` and shares one bucket, so one client can exhaust `account_login` for everybody. Set the real hop count when deploying behind a proxy.
- **Never set it higher than the real chain.** Addresses left of the N-th from the right are written by the client; an over-counted value hands bucket selection back to the attacker. Each counted hop must overwrite or append the header, and the Gunicorn port must be reachable only through those hops.
- **Fail-closed fallback.** If the header is absent, has fewer than N entries, or the selected entry is not a plain IPv4/IPv6 address (hostname, `ip:port`, empty), the request did not come through the declared chain and the identity falls back to `REMOTE_ADDR`. The caller therefore lands in the shared peer bucket (stricter) and can never choose its own key. Proxies that emit `ip:port` must be configured to send a bare address.
- A negative value stops startup. An explicit `REST_FRAMEWORK["NUM_PROXIES"] = None` is treated as `0` by `AccountRateThrottle`; do not rely on that for other DRF throttles, for which DRF reads `None` as "trust the whole header".
- Stock DRF throttles used elsewhere (`ScopedRateThrottle` in authenticated APIs) read the same setting; with N ≥ 1 and a short header DRF itself takes the left-most entry, so anonymous endpoints must use `AccountRateThrottle` or `client_ident`.

With a CDN or load balancer in front of nginx, either let nginx append (`$proxy_add_x_forwarded_for`) and count both hops (`2`), or keep the shipped overwrite with `$remote_addr`, let nginx `real_ip` resolve the client only from **known upstream proxy IP ranges**, and count `1`. Gunicorn does not rewrite `REMOTE_ADDR` from forwarded headers, so `real_ip` alone never changes what Django sees.

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
