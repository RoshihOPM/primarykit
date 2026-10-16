# Redis Cache — независимый переносимый компонент

`apps/cache/` не требует Celery, RabbitMQ, Tasks, Organizations или бизнес-моделей. Он предоставляет настройки штатного `django.core.cache.backends.redis.RedisCache` и небольшие namespace-aware helper-функции. **Источник истины — PostgreSQL**, не Redis.

## Генерация и запуск

```bash
uv run python scripts/new_project.py ../catalog-api --name catalog-api --apps cache
cd ../catalog-api
uv add 'redis>=6,<7'
cp .env.example .env
# в .env: REDIS_CACHE_ENABLED=true, REDIS_CACHE_KEY_PREFIX=catalog-api-dev
docker compose -f compose.yaml -f compose.redis.yaml up -d --build
python -m apps.core.doctor --strict
```

`uv add` выполняется **в клиентском репозитории**, обновляет принадлежащий ему `pyproject.toml` и `uv.lock`, не создаёт зависимости от PrimaryKit. После установки ключи Redis становятся доступны через штатный Django `django.core.cache.cache`, а также функции `apps.cache.services`:

- `get_cached(namespace="tenant:<uuid>", key="listing:<uuid>", default=None)`
- `set_cached(namespace="tenant:<uuid>", key="listing:<uuid>", value=..., timeout=120)`
- `invalidate_cached(namespace="tenant:<uuid>", key="listing:<uuid>")`

Namespace и key хешируются в итоговое имя ключа (без открытых идентификаторов), Redis-доступ идёт через Django CACHES. Scope всегда задаёт вызывающий бизнес-код. Нет автоматического перехвата моделей, межпользовательской видимости или кеширования ответов целиком. Не храните секреты, платежные подтверждения, права пользователей либо tenant grants без предметного security review и осмысленной инвалидации.

## Настройки

- `REDIS_CACHE_ENABLED=false` — по умолчанию используется локальная память процесса, без подключения к Redis.
- `REDIS_CACHE_URL=redis://redis:6379/0` — внутренний адрес Docker в dev; для production используйте `rediss://` с TLS/аутентификацией.
- `REDIS_CACHE_KEY_PREFIX` — обязательный **уникальный** идентификатор проекта при включении Redis, для разделения ключей разных приложений.
- `REDIS_CACHE_TIMEOUT=300` — TTL по умолчанию (1–86400 секунд). В собственном коде вызывайте `set_cached` с явным TTL.

`compose.redis.yaml` — **только для локального/dev**: Redis без пароля в изолированном Docker-сегменте, интерфейс хоста только 127.0.0.1, cache eviction `allkeys-lru`, без персистентности. Не используйте такой контейнер для финансовых ledger, Celery results или хранения сессий без отдельного решения о persistence/security.

## Поведение при сбое

Redis не должен определять истинность записей, прав или финансовых операций. При недоступности Redis стандартный backend Django может выдавать исключение; согласуйте fallback/error policy для конкретной операции. Не скрывайте сетевые сбои в auth/permissions, не выполняйте `cache.clear()` на совместно используемом Redis. Для нескольких организаций всегда включайте scope в cache key, и при любых изменениях исходных данных инвалидируйте соответствующие ключи.

Для метрик используйте Redis мониторинг latency, rejected_connections, evictions, memory, hit ratio и TTL; для продакшена ограничьте доступ сетью и ACL.
