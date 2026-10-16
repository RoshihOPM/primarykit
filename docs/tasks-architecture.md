# Tasks — переносимая внутренняя очередь фоновых заданий

`apps/tasks/` — самостоятельный модуль **без обязательных Redis/RabbitMQ/Celery**. У него нет HTTP endpoints и привязки к Organizations/Orders/Payments. Модели и история миграций принадлежат **сгенерированному клиентскому проекту**.

## Когда выбирать

База PostgreSQL и отдельный процесс worker подходят для небольшого количества нечастых, достаточно коротких фоновых задач: генерация документов, обработка заявок, некритичные интеграционные действия. При большом потоке, сильных требованиях к задержкам/приоритетам или внешним side effects рассматривайте специализированный брокер, Celery или Django Tasks с промышленным backend.

Django 6 уже включает `django.tasks` — **API описания заданий**, но не production worker. Этот модуль предоставляет независимый минимальный DB-подход, а не принуждает клиентские проекты к какому-либо общему сервису или пакетам PrimaryKit.

## Подключение

```bash
uv run python scripts/new_project.py ../worker-api --name worker-api --apps tasks
cd ../worker-api
python -m apps.core.doctor --strict
uv sync --locked
uv run python manage.py makemigrations users tasks
uv run python manage.py migrate
```

Если модуль копируется отдельно, достаточно папки `apps/tasks` и базового Core; регистрация — через `manifest.py`.

## Регистрация и очередь

Реальные обработчики и правила выполнения — **собственный код бизнеса**, например `apps/leads/jobs.py`:

```python
def send_lead_notice(payload: dict):
    lead_id = payload["lead_id"]
    # Перечитать свою БД, проверить актуальное состояние, безопасно выполнить side effect.
```

В настройках **этого проекта**:

```python
BACKGROUND_JOB_HANDLERS = {
    "leads.notice": "apps.leads.jobs.send_lead_notice",
}
```

Внутренний сервис проекта вызывает:

```python
from apps.tasks.services import enqueue

enqueue(
    code="leads.notice",
    payload={"lead_id": str(lead.id)},
    namespace="organization:" + str(org.id),
    idempotency_key="notice:" + str(lead.id),
)
```

`enqueue` использует текущую Django транзакцию: при откате внешней транзакции задание не сохранится. Повтор с тем же `(namespace, idempotency_key)` и идентичными параметрами вернёт существующую запись, конфликт вернёт ошибку. Не отправляйте в `payload` секреты и личную информацию без оценки риска: payload хранится в БД, включая историю после выполнения.

Запуск worker отдельно от HTTP-сервера:

```bash
uv run python manage.py run_background_jobs
uv run python manage.py run_background_jobs --once
uv run python manage.py run_background_jobs --max-jobs 100 --poll-seconds 1
```

В production supervisor / Docker Compose должен перезапускать процесс worker после аварии. У каждого worker нужен отдельный Django процесс и соединение PostgreSQL.

## Семантика и гарантии

- Доставка **at least once**. Повтор возможен после падения worker, истечения lease или исключения в обработчике. **Не** гарантируется exactly-once выполнение внешнего API.
- PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` позволяет нескольким worker забирать разные строки без гонок. SQLite годится лишь для небольших тестов.
- `lease_token` не даёт старому worker завершить повторно захваченное задание. Но уже совершённый side effect может выполниться дважды.
- `run_after` должен быть timezone-aware. Обработчики синхронные и должны иметь собственные таймауты.
- До 10 попыток; повтор после задержки (ограниченный экспоненциальный backoff), после исчерпания — `failed`. Ошибка сохраняет **только тип исключения**, без секретов из сообщения.
- Задача выполняется только если `code` есть в доверенном `BACKGROUND_JOB_HANDLERS`. Ни HTTP-пользователь, ни содержимое JSON не выбирают Python import path.
- Долгие задачи требуют увеличения `--lease-seconds` по сравнению с верхней границей времени выполнения и настройки graceful shutdown, либо полноценного брокера/heartbeats.

**Ограничения:** нет UI для переисполнения failed, DLQ с ручным подтверждением, cron, приоритетов, rate limits, распределённой трассировки, task cancellation, обязательного audit события или автоматической очистки. Настройте мониторинг `failed`, возраста `pending`, числа попыток, бэкапы и retention; не применяйте этот модуль как универсальную финансовую транзакционную шину.

## Дальнейшая кастомизация

Клиент может заменить этот контекст целиком на Celery, Django Tasks с поддерживаемым backend или собственную очередь. От PrimaryKit в runtime нет никаких зависимостей. Не меняйте существующую историю миграций при переходе: нужен новый план данных и cutover.
