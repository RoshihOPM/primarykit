# Как добавить свой переносимый модуль

Пример: независимый `reviews`, который будет работать без Catalog, а при наличии Catalog может показывать его товары.

## 1. Создайте папку

```text
apps/reviews/
├── __init__.py
├── apps.py
├── manifest.py
├── domain.py
├── models.py
├── services.py
├── serializers.py
├── views.py
├── urls.py
├── statistics.py          # по желанию
└── tests/
    ├── __init__.py
    └── test_reviews.py
```

Укажите `AppConfig.name = "apps.reviews"`. В `models.py` используйте UUID-модели Core и `settings.AUTH_USER_MODEL` для owner FK; не добавляйте обязательные foreign keys на optional apps.

## 2. Объявите manifest

```python
from apps.core.module_registry import Module, Route

MODULE = Module(
    name="reviews",
    requires=("users",),
    optional=("catalog", "statistics", "audit"),
    routes=(Route("api/v1/reviews/"),),
    priority=90,
)
```

Теперь `apps/reviews/` распознаётся автоматически. Root `INSTALLED_APPS` и `urls.py` редактировать не нужно. Не используйте `app.ready()` для неожиданных изменений БД.

## 3. Спроектируйте доменные правила

В `domain.py` разместите функции и value objects без Django/DRF или импортов соседних бизнес-модулей. Пример: оценка должна быть 1–5, а текст — не длиннее заданного лимита. Django model хранит факт. Сервис должен проверять owner, наличие связанной сущности и все инварианты повторно внутри транзакции.

Для `source_catalog_id` (если он нужен) можно хранить opaque UUID и валидировать его в **необязательном адаптере**, импортируя Catalog только при установленном приложении. В `services.py` заранее определите scope: personal/tenant/system.

## 4. API и приватность

- DRF serializer валидирует формат входа и доступные foreign identifiers.
- ViewSet ограничивает QuerySet по текущему пользователю; права на объект повторно проверяются в сервисах.
- `transaction.atomic` для команд. Idempotency key + DB unique constraint там, где повтор запроса может дублировать действие.
- Не выдавайте обычному пользователю системную или корпоративную информацию. Глобальный Django superuser не получает права на чужой личный объект автоматически.
- Внешние side-effects (email/S3/провайдеры платежей) — через явные адаптеры. Не путайте успешный HTTP-запрос с доказательством успешной оплаты.

## 5. Опциональная статистика

Добавьте `statistics.py` с `Provider(code="reviews", metrics=(Metric(...),))` из `apps.statistics.domain`. Файл будет импортирован только при наличии установленного Statistics. Фильтруйте по `context.actor` или `context.organization`, считайте только разрешённые строки и не обращайтесь к БД при импорте модуля. [Подробно](statistics-architecture.md).

## 6. Тесты и проверки

```bash
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check --settings=config.settings.test
uv run pytest apps/reviews
```

Минимальный набор тестов: CRUD и доменные правила, недоступность чужих записей (включая superuser), невалидные UUID, повтор команды/идемпотентность, отсутствие optional apps, генератор в нужном составе и реальная PostgreSQL-транзакция для конкурентных денежных/складских операций. Для приложений со схемой БД тестируйте генерацию миграций в новом проекте.

Для проверки копирования используйте CLI генератора, например `--apps reviews`, и убедитесь, что `apps/reviews` запустится без ручных правок `config/`. `scripts/new_project.py` автоматически получает выбор из manifest registry. В `apps/core/tests/test_project_generator.py` добавьте вариант выбранных приложений.

## 7. Документация и PR

В `docs/` добавьте: назначение, API и request samples, права, зависимости, модели и миграции, ограничения. В [modules.md](modules.md) добавьте строку модуля. Обновите `README.md`, если появилось крупное направление. PR должен пройти Ruff, pytest, генерируемые проекты, Docker, PostgreSQL; для Storage — и S3 provider integration.

Не меняйте схему у работающего клиента переключением settings без миграции данных. Оригинальные initial migrations клиента должны храниться в его Git.
