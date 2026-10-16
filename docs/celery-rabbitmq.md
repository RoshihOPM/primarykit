# Celery + RabbitMQ — необязательный backend фоновых задач

`apps/celery_tasks/` — отдельный переносимый адаптер к стандартному Celery, **не зависимый** от `apps/tasks` (PostgreSQL queue) и `apps/cache`. Каждый сгенерированный продукт владеет своими `tasks.py`, бизнес-командами, очередями и настройками retry. RabbitMQ рекомендован как брокер, Redis **опционально** используется как хранилище результатов; Redis Cache работает отдельно от Celery.

## Подключение

```bash
uv run python scripts/new_project.py ../crm-worker-api --name crm-worker-api --apps celery_tasks
cd ../crm-worker-api
uv add 'celery>=5.6,<6'
cp .env.example .env
# замените dev credentials, установите CELERY_BROKER_URL (AMQP URI)
docker compose -f compose.yaml -f compose.celery.yaml up -d --build
```

Этот `uv add` выполняется в новом репозитории, без Python-зависимости на PrimaryKit. Код приложения регистрирует собственные `@shared_task` в своих `apps/<business>/tasks.py`. Команда worker:

```bash
DJANGO_SETTINGS_MODULE=config.settings.local celery -A apps.celery_tasks.celery_app:app worker -l INFO
```

`CELERY_BROKER_URL` обязателен для запуска worker, а при обычном Django startup сетевых подключений к RabbitMQ нет. `CELERY_RESULT_BACKEND` можно оставить пустым (результаты по умолчанию игнорируются). Для Redis результатов Celery 5.6 устанавливайте совместимый набор `uv add 'celery[redis]>=5.6,<6' 'redis>=6.2,<6.5'`. Не пытайтесь без проверки одновременно использовать redis-py 8.x: действующие версии Kombu могут ограничивать redis-py. Самостоятельный CacheService работает с этой совместимой версией Redis. Для Redis Cache-only без Celery можно использовать `redis>=8,<9`. Если бизнесу нужны статусы или значения — включите `redis://...` / `rediss://...` **отдельным Redis DB/instance** с подходящей политикой сохранения данных (не используют dev Redis с `allkeys-lru` и `appendonly no`).

RabbitMQ с локальным паролем из `.env` и портом только на 127.0.0.1 предоставляется `compose.celery.yaml`; `compose.celery.prod.yaml` предназначен для compose.prod.yaml и собирает production target без bind mounts. В production нельзя использовать примерные учетные данные или public management port; используйте TLS, отдельного пользователя/vhost, ограничения памяти/диска, мониторинг очередей и DLQ.

## Корректная публикация

В транзакциях используйте `apps.celery_tasks.dispatch.send_after_commit(task, id, ...)`: событие публикуется **только после commit PostgreSQL**. Это предотвращает обработку незафиксированных данных, но **не гарантирует доставку** при падении API или недоступности брокера после commit.

Для бизнес-критичных событий используйте transactional outbox (или DB-backed Tasks с осмысленным use-case), идемпотентный consumer, наблюдение за stuck/pending состояниями. Celery с `acks_late` и повторной доставкой является at-least-once, внешний запрос может выполняться повторно.

## Защита и эксплуатация

- `CELERY_ACCEPT_CONTENT=["json"]`, никаких pickle/task names из публичного HTTP-поля.
- Задачи должны принимать идентификаторы, перечитывать данные, повторно проверять область прав; не переносить JWT/пароли через брокер.
- Установлены prefetched=1, acks_late, reject_on_worker_lost, soft/hard time limits. Бизнесовые таймауты и повторы конфигурируются для отдельных задач.
- Не включайте одновременно два обработчика для одного business-event без дедупликации. PostgreSQL Tasks и Celery можно выбрать независимо.
- `celery beat` и Flower намеренно не запускаются автоматически; если нужны планировщик/мониторинг — добавляйте отдельные процессы после оценки безопасности и HA.
- Контейнерное окружение — опциональный Compose overlay; наличие исходного конструктора не требуется.

## Выбор

| Вариант | Когда выбрать |
| --- | --- |
| `tasks` — PostgreSQL worker | Небольшие нагрузки, минимум инфраструктуры, транзакционная запись |
| `celery_tasks` + RabbitMQ | Масштабирование worker, маршрутизация, ретраи/приоритеты, много событий |
| Redis Cache | Ускорение повторяющихся вычислений/чтений, без гарантий сохранности |

Подробнее: [DB queue](tasks-architecture.md), [Redis Cache](redis-cache.md), [independent projects](independent-projects.md).
