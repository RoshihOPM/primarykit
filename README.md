# PrimaryKit

Личный конструктор Django backend-проектов с переиспользуемым исходным кодом.

Архитектурный ориентир — [djancore](https://github.com/vathna-vuthy/djancore), но PrimaryKit развивается независимо. **Core** — обычный Django-проект в `config/`, `apps/` — каталог прикладных модулей.

## Stack

Python 3.13 · Django 6.1 · Django REST Framework · PostgreSQL 17 · uv · Docker Compose · Gunicorn · pytest-django · Ruff.

## Локальный запуск с Docker

1. Скопируйте `.env.example` в `.env` и измените значения по необходимости.
2. Запустите `docker compose up --build -d`.
3. **Для нового проекта один раз** сгенерируйте миграцию пользователя:
   `docker compose exec api python manage.py makemigrations users audit storage`
4. Выполните `docker compose exec api python manage.py migrate`.
5. Проверьте `http://localhost:8000/health/live/` и `http://localhost:8000/health/ready/`.
6. Создайте администратора: `docker compose exec api python manage.py createsuperuser`.

Это исходный **конструктор**, поэтому миграции пользовательских приложений не хранятся в каталоге PrimaryKit. В созданном из него проекте **обязательно коммитьте полученные миграции** до первого развёртывания.

## Локальный запуск через uv

```bash
cp .env.example .env
docker compose up -d db
uv sync --locked
uv run python manage.py makemigrations users audit storage
uv run python manage.py migrate
uv run python manage.py runserver
```

Локальный Postgres пробрасывается только на 127.0.0.1:5432. В Windows PowerShell вместо `cp` можно использовать `Copy-Item`.

## Контроль качества

```bash
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check --settings=config.settings.test
uv run python manage.py makemigrations users --settings=config.settings.test
uv run pytest
```

## Production

Сборка отдельного production-образа: `docker build --target production -t primarykit:latest -f docker/Dockerfile .`.

В `compose.prod.yaml` используется `config.settings.production`. До запуска задайте реальный `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` и `DJANGO_CSRF_TRUSTED_ORIGINS`. Приложение слушает localhost:8000 для Nginx. HTTPS завершается на доверенном reverse proxy; `DJANGO_TRUST_PROXY_SSL_HEADER=true` допустим **только если** proxy гарантированно перезаписывает X-Forwarded-Proto.

Инициализация нового окружения: генерация миграций **до сборки**, затем `docker compose -f compose.prod.yaml run --rm api python manage.py migrate` и `collectstatic`. Продакшену нужны надёжные резервные копии PostgreSQL, TLS, мониторинг, хранение статических файлов и отдельные секреты.

## Что уже есть

- Разделение настроек и обязательные production-проверки.
- DRF, CORS, Swagger/Redoc в local, единые ошибки и пагинация.
- Liveness/readiness с проверкой БД.
- Минимальный email-based `users.User` до первой миграции.
- Dev/production Docker targets, Compose и CI.

## Что будет позже

Wallets, chats, payments, catalog, inventory. Эти функции реализуются поэтапно; актуальный состав — ниже.

Соглашения по переносимым модулям — в [docs/architecture.md](docs/architecture.md).
## Architecture and Agent Skills

- [Core conventions: models, services/selectors and localization](docs/core-conventions.md)
- [Repository rules for agents](AGENTS.md)
- [Agent workflow and evaluated external skills](docs/agent-workflow.md)
- [Modular monolith architecture decision](docs/adr/0001-copy-based-modular-monolith.md)
- [Catalog / inventory design backlog](docs/module-roadmap.md)

Agent Skills: `.agents/skills/system-architect/`, `.agents/skills/database-architect/`, `.agents/skills/feature-delivery/`. These are guidance files, **not** a deployed multi-agent runner. The catalog/inventory modules remain future work.

Core now exposes opt-in `SoftDeleteModel` and `SoftDeleteUUIDTimestampedModel` with separate active/unfiltered managers; see the documented caveats about cascades, uniqueness, and bulk operations.

## Users API v0.1 and security

[Users API, authorization model and deployment limitations](docs/users-architecture.md).
The endpoints include JWT login/refresh/logout, account profile, password change, optional registration, and superuser administration.
Authentication changes must pass the [.agents security-review skill](.agents/skills/security-review/SKILL.md).
Public registration is off by default. **Do not deploy public authentication without shared-cache / edge-layer brute-force controls.**

## RBAC module

RBAC reuses Django Groups and Permissions (no duplicate role model). An active superuser manages roles and assignments at `/api/v1/admin/rbac/`. Default `RBAC_ASSIGNABLE_PERMISSIONS = []` denies permission grants until the new project sets an allowlist.

See [RBAC architecture and object scoping](docs/rbac-architecture.md). The built-in owner-only scoping helper prevents IDOR for explicitly configured views; arbitrary per-object ACL and multi-tenant role grants are **not included**.

## Notifications and account recovery

[Email notifications, verification and password reset](docs/email-notifications.md).

`apps/notifications` provides reusable Django 6.1 MAILERS-based templated email. `users` issues signed, expiring single-use verification/password-reset tokens. **Email flows are disabled by default**. Configure the mailer, frontend callback URLs, and registration settings before enabling public signups; use shared rate limits and email-abuse protections in production.

## Audit Events

Audit logs are written in the same database transaction as identity and RBAC changes.
The `apps.audit` app exposes read-only, superuser-only endpoints at
`/api/v1/admin/audit/events/` and an opt-in audit service for other modules.
See [audit architecture and limitations](docs/audit-architecture.md).

**Migration setup for new project:** `python manage.py makemigrations users audit`
before `migrate`, and **commit generated migrations in that project**.

## Private Storage

A secure owner-scoped upload/download API is available at `/api/v1/files/` with
PDF/PNG/JPEG/WebP magic-byte verification, safe random object keys, read-only
metadata and no public storage URLs. See [storage architecture](docs/storage-architecture.md).

Use `STORAGE_BACKEND=local` for development. Production requires an explicitly
persistent local volume (`STORAGE_ALLOW_LOCAL_PRODUCTION=true`) or
`STORAGE_BACKEND=s3` and an installed `django-storages[s3]` backend (e.g.
`uv add 'django-storages[s3]'` in the generated project). S3-compatible
SeaweedFS/MinIO endpoints are supported by the backend but require a live provider
integration test in each deployment.
