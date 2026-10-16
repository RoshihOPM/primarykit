# CacheService — типизированный Redis cache для независимых Django backend

**Рекомендуемый путь:** `apps.cache.services.CacheService` поверх официального `redis-py`. Модуль `apps/cache` переносится копированием без runtime-зависимости от PrimaryKit. Redis **не** заменяет PostgreSQL и не хранит авторитетные права, деньги, остатки или историю заказов.

Новый код не обязан использовать `django.core.cache`. Django Cache и `django-redis` — только **необязательные** интеграции для пакетов, которым необходим Django Cache API.

## Установка

Для отдельного Redis Cache (без Celery):

```bash
uv run python scripts/new_project.py ../catalog-api --name catalog-api --apps cache
cd ../catalog-api
uv add 'redis>=8,<9'
cp .env.example .env
# выставить REDIS_CACHE_ENABLED=true, REDIS_CACHE_KEY_PREFIX=catalog-api-dev
docker compose -f compose.yaml -f compose.redis.yaml up -d --build
python -m apps.core.doctor --strict
```

Redis создаётся только при вызове фабрики, подключение — при первой сетевой команде. Если Redis выключен или пакет не установлен, фабрика выдаёт явную ошибку, **не возвращает автоматически локальный кэш**. Другие модули и API Django работают без Redis.

Для **совместного Celery 5.6 + Redis result backend** используйте совместимый набор:

```bash
uv add 'celery[redis]>=5.6,<6' 'redis>=6.2,<6.5'
```

На октябрь 2026 совместное безусловное повышение до redis-py 8.x конфликтует с ограничениями некоторых версий Kombu; CacheService специально использует стандартные команды, работающие с redis-py 6.x и 8.x. Если Celery работает с RabbitMQ **без Redis result backend**, ставьте его без extra Redis: `uv add 'celery>=5.6,<6'`, тогда cache-only Redis 8.x устанавливается отдельно. Все версии фиксируются **в собственном uv.lock клиента**.

## Native API

```python
from apps.cache.services import get_cache_service

cache = get_cache_service()
cache.set_json("listing:123", {"price": 15000000}, ttl=300, namespace="tenant:uuid")
cache.get_json("listing:123", namespace="tenant:uuid", default=None)

cache.hash_set(
    "listing:123",
    {"brand": "Hyundai", "price": 15000000, "views": 0},
    ttl=300,
    namespace="tenant:uuid",
)
cache.hash_get("listing:123", "price", namespace="tenant:uuid")
cache.hash_getall("listing:123", namespace="tenant:uuid")
cache.hash_increment("listing:123", "views", ttl=300, namespace="tenant:uuid")
cache.hash_delete("listing:123", "price", namespace="tenant:uuid")

cache.increment("listing-views:123", ttl=300, namespace="tenant:uuid")
cache.delete("listing:123", kind="hash", namespace="tenant:uuid")
```

`get_cache_service()` возвращает переиспользуемый redis-py клиент/connection pool для сочетания URL и prefix внутри процесса. Для чистых unit tests можно передать fake/mock redis-клиент через `CacheService(fake, prefix="test-env")`.

- `set_json/get_json`: JSON с `allow_nan=False`, не более 256 KiB; no pickle.
- `hash_set/hash_get/hash_getall/hash_delete`: JSON значения отдельных полей, имена полей — короткие ASCII идентификаторы (не PII).
- `increment/hash_increment`: нативные Redis `INCRBY/HINCRBY`; для корректности счётчика используйте только **целые числа** (не bool/float) и не переключайте тип того же поля на строку.
- TTL обязателен при каждой записи, 1–86400 секунд. Hash+EXPIRE и increment+EXPIRE отправляются одной Redis-транзакцией `MULTI/EXEC`. При повторной записи TTL продлевается.
- Формат ключа `<project-prefix>:<type>:v1:<sha256(namespace + delimiter + logical_key)>`; тем самым идентификаторы и email не отражаются в сырых именах Redis. Между JSON, Hash и Counter нет коллизии типов.
- Redis error не проглатывается. Используйте отказоустойчивый fallback на **авторитетную БД** только если допустимо для данного use-case. Нельзя считать timeout подтверждением мутации данных.
- Никаких запросов из `AppConfig.ready()`, автоматической синхронизации ORM, глобального `cache.clear()` и сканирования всех ключей.

## Опциональные Django адаптеры

Для стороннего Django-пакета, которому нужен `django.core.cache`, включите в `.env`:

```dotenv
REDIS_CACHE_DJANGO_BACKEND=django
```

Значение `django` использует стандартный `django.core.cache.backends.redis.RedisCache`. При `django-redis` нужно отдельно установить `uv add 'django-redis>=7,<8'` и проверить совместимость с **Django 6.1** на своём CI (7.0.0 официально перечисляет Django 5.2/6.0, но не 6.1). Настройка `none` — значение по умолчанию: собственный сервис не перехватывает `CACHES`.

Сохранены старые `get_cached/set_cached/invalidate_cached` на Django Cache для уже скопированных клиентских проектов; **новый код должен использовать CacheService**.

## Отдельная инфраструктура

В `compose.redis.yaml` Redis без авторизации используется **только в dev** и доступен на хосте исключительно через `127.0.0.1`. Для production настройте ACL, TLS/`rediss://`, изоляцию сети и ключей по проекту, мониторинг памяти/evictions/TTL. TTL, namespace и параметры доступа принадлежат **клиентскому backend**, а не общему PrimaryKit.

Redis cache не обеспечивает ровно однократное выполнение или долговечность финансового ledger. Если нужны Celery worker, RabbitMQ и Redis results, см. [Celery](celery-rabbitmq.md). Если достаточно DB-backed worker — [Tasks](tasks-architecture.md).
