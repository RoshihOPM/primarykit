# Каталог переносимых модулей

PrimaryKit распознаёт любую доверенную папку `apps/<name>/` с `__init__.py`, `apps.py` и `manifest.py`. Модуль включается автоматически, если его обязательные зависимости установлены. Для новых приложений можно использовать `python manage.py install_kit_module <name> --source ../primarykit`.

## Что можно подключить

| Имя | Бизнес-назначение | Обязательные зависимости* | Optional integration |
| --- | --- | --- | --- |
| `core` | Соглашения и registry | — | — |
| `feature_flags` | Локальные feature flags для контролируемых релизов | core | — |
| `search` | PostgreSQL text search с явной фильтрацией owner/tenant | core | — |
| `csv_exchange` | Схемонезависимый безопасный CSV parse/export | core | — |
| `api_keys` | Scoped машинные ключи с owner scope и отзывом | users | audit |
| `idempotency` | PostgreSQL идемпотентность команд с атомарным replay | core | — |\n| `usage_quotas` | Атомарные квоты потребления, owner/tenant, снимки политик | users | organizations, statistics |
| `http_integrations` | Явно разрешённые HTTPS host + безопасный retry | core | — |
| `tasks` | Внутренняя очередь, транзакционное добавление и worker | core | — |
| `outbox` | Транзакционная запись событий и retry delivery через Tasks | core, tasks | — |
| `webhooks` | HMAC inbound receipts and outbound delivery | core, outbox | — |
| `cache` | Native redis-py CacheService, JSON, Hashes, counters; optional Django Cache bridge | core | — |
| `rate_limit` | Redis-backed shared authentication protection | core, cache | — |
| `observability` | Correlation IDs, structured HTTP access logs | core | — |
| `celery_tasks` | Celery adapter, RabbitMQ и необязательный Redis result backend | core | — |
| `users` | JWT, профиль, email auth | core, notifications | audit |
| `notifications` | Шаблонные email | core | — |
| `organizations` | Компании, филиалы, участники | users | audit |
| `rbac` | Django Groups/Permissions | users | — |
| `audit` | Неизменяемый журнал | users | — |
| `storage` | Приватные личные/корпоративные файлы | users, core | organizations, audit |
| `catalog` | Категории, товары, атрибуты | users | organizations, audit |
| `inventory` | Склады, SKU, остатки и резервы | users | catalog, organizations, audit |
| `statistics` | Read-only метрики установленных модулей | users | catalog, inventory, storage, organizations |
| `orders` | Снимок состава заказа, статус | users | catalog, sales, payments, audit |
| `sales` | Учёт продажи, аннулирование | users | orders, payments, inventory, audit |
| `payments` | Намерение оплаты и сверка | users | orders, sales, audit |

* `users`, `core` и `notifications` уже входят в каждый проект. Все не перечисленные в колонке обязательных интеграций модули могут работать друг без друга.

## Основные API

| Имя | URL prefix | Роль |
| --- | --- | --- |
| Users | `/api/v1/` | JWT/аккаунт |
| Storage | `/api/v1/files/` | Личные файлы |
| Organizations | `/api/v1/organizations/` | Организации |
| Catalog | `/api/v1/catalog/` | Standalone |
| Inventory | `/api/v1/inventory/` | Standalone |
| Orders | `/api/v1/orders/` | Пользователь |
| Sales | `/api/v1/sales/` | Пользователь |
| Payments | `/api/v1/payments/` | Пользователь |
| Payments manual reconcile | `/api/v1/admin/payments/` | Только суперпользователь |
| Statistics | `/api/v1/statistics/` | Только доступные метрики |

Usage Quotas предоставляет только серверные сервисы, без публичного API выдачи квот. Tasks, Cache и Celery не создают публичных API маршрутов; Celery и Redis не устанавливаются в клиенте автоматически. Tasks не создаёт публичных API маршрутов: `enqueue` вызывается только из доверенного кода приложения; worker запускается отдельно.

Доступные маршруты можно увидеть после старта в Swagger `/api/docs/` (DEBUG). Если Organizations и нужные приложения включены в **tenant** режиме, Catalog и Inventory регистрируют корпоративные префиксы `/api/v1/organizations/{org_id}/catalog/` и `inventory/`. Statistics также имеет tenant и system API.

## Подходы к сборке

**Личный проект:**

```bash
uv run python scripts/new_project.py ../solo-api --name solo-api \
  --apps catalog inventory orders sales payments statistics
```

**Корпоративный проект:**

```bash
uv run python scripts/new_project.py ../b2b-api --name b2b-api \
  --apps organizations catalog inventory storage audit statistics orders sales payments
```

Важное различие: в этом релизе Orders, Sales, Payments остаются **личными** модулями (не имеют company FK и не предоставляют company-owned товарооборот). Они могут быть установлены в B2B-проект, но не становятся автоматически многопользовательскими учётными системами. Для реального tenant Commerce нужна отдельная модель прав, команд и миграций.

## Модель интеграций

- Наличие `orders` не является требованием для `sales` и `payments`. При его наличии можно указать `source_order_id`. Сервис проверит, что заказ принадлежит текущему пользователю и сумма/валюта совпадают.
- Платежи не проводят эквайринг. Запрос на оплату всегда создаётся `pending`; подтверждение доступно только через привилегированную сверку. Нельзя использовать эту версию для публичного приема денег.
- `statistics` автоматически обнаруживает `statistics.py` выбранных модулей. Для новых Orders, Sales и Payments доступны свои метрики пользователя.
- `inventory` не изменяется автоматически при записи `sale` и `order`. Списание остатков требует отдельного use-case с идемпотентностью и согласованным резервированием.
- `catalog` и `inventory` standalone не связывают SKU друг с другом автоматически; это разные контексты.

**Важное правило:** `CATALOG_MODE` и `INVENTORY_MODE` фиксируются до первого `makemigrations`. Нельзя менять их у работающей БД простым флагом.

Подробнее: [Commerce](commerce-architecture.md), [Statistics](statistics-architecture.md), [Architecture](repository-guide.md).
