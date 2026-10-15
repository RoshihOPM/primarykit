# PrimaryKit

Личный конструктор Django backend-проектов с переиспользуемым исходным кодом.

Архитектурный ориентир — [djancore](https://github.com/vathna-vuthy/djancore), но PrimaryKit развивается независимо. **Core** — обычный Django-проект в `config/`, `apps/` — каталог прикладных модулей.

## Stack

Python 3.13 · Django 6.1 · Django REST Framework · PostgreSQL 17 · uv · Docker Compose · Gunicorn · pytest-django · Ruff.

## Локальный запуск с Docker

1. Скопируйте `.env.example` в `.env` и измените значения по необходимости.
2. Запустите `docker compose up --build -d`.
3. **Для нового проекта один раз** сгенерируйте миграцию пользователя:
   `docker compose exec api python manage.py makemigrations users`
4. Выполните `docker compose exec api python manage.py migrate`.
5. Проверьте `http://localhost:8000/health/live/` и `http://localhost:8000/health/ready/`.
6. Создайте администратора: `docker compose exec api python manage.py createsuperuser`.

Это исходный **конструктор**, поэтому миграции пользовательских приложений не хранятся в каталоге PrimaryKit. В созданном из него проекте **обязательно коммитьте полученные миграции** до первого развёртывания.

## Локальный запуск через uv

```bash
cp .env.example .env
docker compose up -d db
uv sync --locked
uv run python manage.py makemigrations users
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

API регистрации/JWT, RBAC, storage, audit, notifications, wallets, chats, payments. Эти функции **ещё не реализованы**.

Соглашения по переносимым модулям — в [docs/architecture.md](docs/architecture.md).