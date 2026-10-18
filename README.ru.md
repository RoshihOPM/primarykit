# PrimaryKit

**Язык:** Русский · [English](README.md)

**Лицензия:** [MIT](LICENSE) · [Участие в разработке](CONTRIBUTING.md) · [Безопасность](SECURITY.md) · [Кодекс поведения](CODE_OF_CONDUCT.md) · [Инструкция по защите main](docs/maintainer-playbook.md)

> Текущая версия исходников: `0.1.0` (активная разработка). Реализованные модули не означают готовность каждой бизнес-функции к production без проверки и интеграции.


**PrimaryKit — конструктор Django REST API из переносимых модулей.** Выбираешь готовый функционал (пользователи, каталог, склад, заказы, продажи, платежи, файлы, статистика), создаёшь проект или копируешь папку модуля, фиксируешь миграции и запускаешь собственный backend.

Это **каталог исходников + генератор проектов**, а не SaaS, не микросервисная платформа и не пакет, который автоматически обновляет все клиентские приложения. **Созданный backend не зависит от исходного PrimaryKit**: без runtime-импортов, общего сервера или обязательных обновлений. Сгенерированный проект независим: он владеет своим кодом, миграциями, инфраструктурой и релизами. Типовые бизнес-модули являются исходными примерами, а не едиными правилами для каждого бизнеса.

## Быстрый старт

Нужны Python 3.13, `uv`, Git и PostgreSQL (для Docker-сценария также Docker Compose).

```bash
git clone https://github.com/RoshihOPM/primarykit.git
cd primarykit
uv sync --locked
uv run python scripts/new_project.py ../shop-api --name shop-api --apps catalog inventory orders sales payments statistics --git-init
cd ../shop-api
cp .env.example .env
docker compose up -d db
uv run python manage.py makemigrations users catalog inventory orders sales payments
uv run python manage.py migrate
python -m apps.core.doctor --strict
uv run python manage.py runserver
```

После запуска: [health/live](http://127.0.0.1:8000/health/live/) и Swagger [api/docs](http://127.0.0.1:8000/api/docs/) (при `DEBUG` в локальных настройках). Миграции нужно **сохранить в Git созданного проекта**. Для Windows PowerShell используйте `Copy-Item .env.example .env` вместо `cp`.

Важно: в команде выше Catalog и Inventory работают в **standalone**-режиме (собственные товары/склады, без Organizations). Для организации/филиалов добавьте `organizations` при генерации проекта **до создания миграций**.

Подробнее: **[Руководство по установке](docs/getting-started.md)**.

## Документация

| Раздел | Для чего |
| --- | --- |
| [Независимые проекты](docs/independent-projects.md) | Правила отсутствия runtime-зависимости, миграций и права на бизнес-логику |
| [Project Doctor](docs/doctor.md) | Offline диагностика локальных модулей и режима схемы |
| [Архитектурные рецепты](docs/architecture-recipes.md) | Примеры для CRM, classifieds, B2B и минимального API |
| [Старт и установка](docs/getting-started.md) | Установка, .env, Docker, uv, миграции, первый API |
| [Каталог модулей](docs/modules.md) | Что даёт каждая папка, обязательные и необязательные зависимости |
| [Как устроена репа](docs/repository-guide.md) | Архитектура, manifest, Django/DDD, переносимость |
| [Создание и подключение модулей](docs/module-development.md) | Пошаговая разработка своего Django-приложения |
| [Генератор проектов](docs/project-generator.md) | CLI-аргументы, пресеты, dry-run, миграции, `--git-init` |
| [Module upgrade check](docs/module-upgrades.md) | Offline diff и анализ риска без перезаписи клиентских файлов |
| [OpenAPI contract check](docs/api-compatibility.md) | Сравнение старой и новой схемы API до клиента |
| [Commerce: Orders, Sales, Payments](docs/commerce-architecture.md) | API, состояния, деньги, инварианты, безопасность |
| [Фоновые задачи](docs/tasks-architecture.md) | Очередь, обработчики клиента, worker, ограничения доставки |
| [Privacy retention](docs/privacy-retention.md) | Клиентские политики, правовые блокировки, dry-run и аудит |
| [Transactional Outbox](docs/outbox-architecture.md) | Durable business events в PostgreSQL Tasks, idempotent dispatch |
| [Signed Webhooks](docs/webhooks.md) | HMAC, PostgreSQL-защита от повторов и исходящие уведомления |
| [Private Chat & Realtime](docs/chat-realtime.md) | Необязательные 1:1 диалоги и WebSocket с reconnect cursor |
| [Redis Cache](docs/redis-cache.md) | Собственный CacheService на redis-py: JSON, Hashes, счётчики и TTL; Django Cache опционален |
| [Distributed Rate Limiting](docs/rate-limiting.md) | Атомарные Redis-лимиты между Django workers |
| [Observability](docs/observability.md) | Request IDs, структурированные JSON-логи, длительность запросов |
| [Celery + RabbitMQ](docs/celery-rabbitmq.md) | Независимый worker, брокер, необязательные результаты Redis |
| [Статистика](docs/statistics-architecture.md) | Как бизнес-модули отдают метрики |
| [Feature Flags](docs/feature-flags.md) | Безопасные feature toggles, не заменяют авторизацию |
| [Search](docs/search.md) | PostgreSQL-поиск с явной областью доступа и лимитами |
| [CSV Exchange](docs/csv-exchange.md) | CSV injection, валидация, лимиты, клиентские транзакции |
| [API Keys](docs/api-keys.md) | Ключи для machine-to-machine авторизации с проверкой permissions |
| [Idempotency](docs/idempotency.md) | Транзакционные ключи от повторных запросов |
| [Device Sessions](docs/device-sessions.md) | Управление JWT-сессиями устройств, отзыв и ограничения access-токенов |
| [PostgreSQL Scheduler](docs/tasks-architecture.md) | Планирование задач с lease fencing и семантикой часовых поясов |
| [Module Scaffold](docs/module-scaffold.md) | Source-only CLI для создания модулей и графа зависимостей |
| [Workflows](docs/workflows.md) | Переносимый state machine, scoped transitions, history и защита от гонок |
| [Usage Quotas](docs/usage-quotas.md) | Бизнес-лимиты и атомарные PostgreSQL-счётчики (opt-in) |
| [HTTP Integrations](docs/http-integrations.md) | Безопасные настройки исходящих HTTPS-запросов |
| [Совместимость модулей](docs/module-compatibility.md) | Контракты, версионирование и ручной перенос исправлений |
| [Production runbook](docs/production-operations.md) | Nginx, резервные копии, релизы и восстановление |
| [Развёртывание](docs/deployment.md) | Dev/prod, nginx, переменные и эксплуатационные ограничения |
| [Правила агентов](AGENTS.md) | Код-стайл, тесты, архитектурные границы |
| [ADR](docs/adr/0001-copy-based-modular-monolith.md) | Решения и архитектурные компромиссы |

[Полный индекс документации](docs/README.md).

## Модули

| Модуль | Что умеет |
| --- | --- |
| **core** | Настройки проекта, абстрактные модели, healthcheck, registry |
| feature_flags | Локальные feature flags без БД и внешних сервисов, выключены по умолчанию |
| search | PostgreSQL full-text search с явным server-side owner/tenant scope |
| csv_exchange | Безопасный ограниченный CSV import/export без изменения БД |
| api_keys | Хешированные API-ключи со scopes, истечением, ротацией и отзывом |
| idempotency | Однократное выполнение PostgreSQL-команд и повторное получение результата |
| workflows | Чистый автомат состояний с разрешениями, guards и необязательной историей переходов |
| usage_quotas | PostgreSQL квоты по владельцу/организации, события расхода, снимки политики |
| http_integrations | Контролируемый HTTPS-клиент сторонних API, retries, ограничения ответов |
| tasks | Внутренняя PostgreSQL-очередь фоновых задач, отдельный worker, повторы и идемпотентность |
| outbox | События бизнеса внутри транзакций PostgreSQL, доставка через Tasks |
| privacy | Политики клиентского хранения PII, dry-run, legal hold и аудит без автоудаления по умолчанию |
| webhooks | Подписанные входящие и исходящие Webhooks с replay protection |
| cache | Native redis-py CacheService (JSON, Hashes и счётчики), необязательный Django Cache bridge |
| rate_limit | Общие Redis-лимиты login/register/password endpoints |
| observability | Генерация request IDs и HTTP метрики в JSON-логах |
| celery_tasks | Отдельный Celery-адаптер с RabbitMQ и необязательным Redis result backend |
| **users** | JWT, email auth, профиль, восстановление, управление сессиями устройств |
| chat | Приватные 1:1 диалоги, сообщения, статусы прочтения и вложения | 
| realtime | Необязательный WebSocket ASGI с JWT и reconnect cursor; без обязательного Redis | 
| **notifications** | Шаблоны писем и email backend |
| organizations | Компании, роли участников, филиалы |
| rbac | Назначение Django Groups/Permissions |
| audit | Неизменяемый журнал действий |
| storage | Приватные файлы, локальный/S3 backend |
| catalog | Категории, SKU, типизированные атрибуты |
| inventory | Склады, остатки, резервы, движение |
| statistics | Автоматическое обнаружение метрик модулей |
| orders | Снимки заказов, цены, отмена |
| sales | Учет записанных продаж и аннулирование |
| payments | Намерения оплаты, ручная привилегированная сверка |

Core, Users и Notifications входят в базовый проект. Все остальные **опциональны**. Orders, Sales и Payments запускаются независимо и не требуют друг друга. Подробнее: [таблица зависимостей и маршрутов](docs/modules.md).

## Два способа использования

**1. Сгенерировать независимый проект:**

```bash
uv run python scripts/new_project.py ../warehouse --name warehouse --apps inventory statistics
```

**2. Скопировать дополнительный модуль в уже созданный PrimaryKit-проект:**

```bash
python manage.py install_kit_module orders --source ../primarykit
python manage.py makemigrations orders
python manage.py migrate
```

Команда копирует нужные папки из доверенного исходника и не перезаписывает код. `INSTALLED_APPS` и URLs собираются автоматически из `manifest.py`. **В произвольном стороннем Django-проекте без базы PrimaryKit простое копирование не гарантируется.**

## Гарантии и границы

- Django + DRF + PostgreSQL, JWT, права доступа на уровне queryset **и** сервисов, PostgreSQL транзакции и idempotency keys там, где это необходимо.
- Catalog и Inventory: `standalone` или `tenant` — схема фиксируется **до первых миграций**. Простое изменение режима у заполненной базы недопустимо.
- Prices в Orders/Sales задаются в **целых минимальных денежных единицах**, это снимки, а не доверенный серверный прайсинг магазина.
- **Payments не интегрирован с реальным эквайрингом.** Создание PaymentIntent не означает, что деньги получены; ручное подтверждение ограничено суперпользователем. Для реального приёма платежей нужны проверяемые webhook-события провайдера, возвраты и финансовая сверка.
- Sales — учёт записи о продаже, **не** автоматическое списание Inventory и **не** кассовый чек/фискализация.
- Cache и Celery полностью опциональны: клиент сам устанавливает `redis`/`celery[redis]`, выбирает Compose overlays и настройки. Redis не является источником истины, а Celery не заменяет транзакционный outbox.
- Для новой установки генерируйте, проверяйте и коммитьте миграции. Не перегенерируйте initial migrations работающего клиентского приложения.
- Секреты в `.env`, production HTTPS, защищённое хранение и резервные копии — ответственность окружения.

## Проверки

```bash
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check --settings=config.settings.test
uv run pytest
```

CI дополнительно проверяет генератор и разные составы модулей, Docker, PostgreSQL и SeaweedFS.

Python 3.13 · Django 6.1 · DRF · PostgreSQL 17 · uv · Docker Compose · pytest · Ruff.

## Разработка с AI-агентами

В сгенерированном проекте запустите `python -m apps.core.agent_context --format markdown` и передайте результат агенту вместе с `AGENTS.md`. Контекст формируется офлайн на основе реально установленных модулей, без БД и сети. См. [AI workflow](docs/ai-assisted-development.md).

## Объявления — отдельно от Catalog

`--apps listings` добавляет черновики, модерацию, публикацию и публичное чтение объявлений. Это не SKU-каталог, модель автомобиля, фотографии или платное продвижение. [Документация](docs/listings.md).
