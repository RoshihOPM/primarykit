# Быстрый старт: от репозитория до собственного API

**Язык:** Русский · [English](en/getting-started.md) · [Оглавление](README.md)


## Что понадобится

Python 3.13, Git, [uv](https://docs.astral.sh/uv/), Docker + Docker Compose (рекомендуется) или установленный PostgreSQL 17. Проект написан на Django 6.1 и DRF. Для локального интерфейса API достаточно браузера, Swagger включён в debug-настройках.

## Вариант A: создать независимый проект из модулей

```bash
git clone https://github.com/RoshihOPM/primarykit.git
cd primarykit
uv sync --locked

# Минимум: core + users + notifications.
uv run python scripts/new_project.py ../my-api --name my-api --git-init

# Или API для магазина:
uv run python scripts/new_project.py ../shop-api --name shop-api \
  --apps catalog inventory orders sales payments statistics audit \
  --git-init
cd ../shop-api
python -m apps.core.doctor --strict
cp .env.example .env
```

Для Windows PowerShell: `Copy-Item .env.example .env`. В `.env` для локального запуска проверьте `DATABASE_URL`, пароль БД и `DJANGO_SECRET_KEY`; не коммитьте секреты. Сгенерированные `pyproject.toml` и `uv.lock` относятся к **новому** проекту.

### Запустить базу и Django

```bash
docker compose up -d db
uv sync --locked
# Для данного примера выбраны следующие app labels:
uv run python manage.py makemigrations users audit catalog inventory orders sales payments
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Миграции могут включать только реально выбранные приложения: укажи их labels в `makemigrations`, **всегда включая users для custom User**. Statistics не создаёт таблиц. Catalog/Inventory должны иметь выбранный schema mode до первого `makemigrations`. Закоммить сгенерированные файлы `apps/*/migrations/` в репозитории `my-api`.

Проверка:

```bash
curl http://127.0.0.1:8000/health/live/
```

Swagger: `http://127.0.0.1:8000/api/docs/` при `config.settings.local`, если DEBUG включён. Авторизация API — JWT. Получить токен можно через Users endpoints; см. [Users API](users-architecture.md). Обычные пользовательские API защищены авторизацией.

## Вариант B: запустить исходный каталог для разработки

```bash
git clone https://github.com/RoshihOPM/primarykit.git
cd primarykit
cp .env.example .env
uv sync --locked
docker compose up -d db
uv run python manage.py makemigrations users organizations audit storage catalog inventory orders sales payments
uv run python manage.py migrate
uv run python manage.py runserver
```

**Исходный репозиторий — конструктор.** Готовый backend не содержит runtime-зависимости от PrimaryKit; его исходники, зависимости и бизнес-правила принадлежат отдельному продукту. См. [правила независимости](independent-projects.md) и [doctor](doctor.md).

 Миграции его business apps намеренно не коммитятся: для разработки они генерируются локально. В клиентском проекте после первого создания и деплоя **никогда не удаляйте и не пересоздавайте миграции без плана**.

```bash
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check --settings=config.settings.test
uv run pytest
```

## Как добавить один модуль позднее

В созданном ранее проекте:

```bash
python manage.py install_kit_module orders --source ../primarykit --dry-run
python manage.py install_kit_module orders --source ../primarykit
python manage.py makemigrations orders
python manage.py migrate
```

Или скопировать `apps/orders/` вручную: Django автоматически обнаружит его `manifest.py` и URLs при следующем запуске. Базовые Core/Users/Notifications должны уже быть. Команда не скачивает пакеты, не обновляет исходные папки, не выполняет миграции и не деплоит сервисы.

**Особенности Catalog/Inventory:** в проекте есть `CATALOG_MODE` / `INVENTORY_MODE`. Прежде чем впервые добавить эти модули, убедитесь, что выбран верный `standalone` или `tenant` режим. После создания таблиц менять режим нельзя без отдельной миграции данных. Подробнее [ADR 0005](adr/0005-standalone-catalog-inventory.md).

## Типичные проблемы

- `relation ... does not exist`: не созданы или не применены миграции нового приложения.
- `Required module ... is missing`: нарушены обязательные зависимости `manifest.py`.
- Неверная схема Catalog/Inventory: пересмотрите MODE **до создания таблиц**, а на проде — спланируйте миграцию.
- API отвечает 401: отсутствует JWT / учётная запись не прошла правила верификации.
- API отвечает 404 на чужой объект: ожидаемое поведение защиты от IDOR.
- PostgreSQL не доступен: проверьте `docker compose ps` и `DATABASE_URL`.
- S3 не доступен: проверьте конфигурацию Storage отдельно, Statistics/Orders от S3 не зависят.

Продолжение: [каталог модулей](modules.md) · [пишем свой модуль](module-development.md) · [продакшен](deployment.md).
