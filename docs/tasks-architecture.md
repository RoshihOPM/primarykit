# Tasks — переносимая внутренняя очередь фоновых заданий

**Язык:** Русский · [English](en/tasks-scheduler.md) · [Оглавление](README.md)


`apps/tasks/` — самостоятельный модуль **без обязательных Redis/RabbitMQ/Celery**. Для отдельного брокера и масштабирования worker теперь доступен полностью опциональный [Celery + RabbitMQ](celery-rabbitmq.md), а [Redis Cache](redis-cache.md) не зависит ни от одной очереди. У него нет HTTP endpoints и привязки к Organizations/Orders/Payments. Модели и история миграций принадлежат **сгенерированному клиентскому проекту**.

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

**Ограничения:** нет UI для переисполнения failed, DLQ с ручным подтверждением, cron-expressions, приоритетов, rate limits, распределённой трассировки, task cancellation, обязательного audit события или автоматической очистки. Настройте мониторинг `failed`, возраста `pending`, числа попыток, бэкапы и retention; не применяйте этот модуль как универсальную финансовую транзакционную шину.

## Повторяющиеся расписания — PostgreSQL scheduler

Необязательный планировщик живёт **внутри `apps/tasks`**, использует тот же
`BackgroundJob` и не создаёт отдельную очередь. Для расписаний добавлена
таблица `JobSchedule` (уникальное имя в `namespace`, статус активности,
временная зона, локальное время, дни недели, `next_run_at`, payload,
лимит попыток). Индекс `(is_enabled, next_run_at)` ускоряет выборку.

В коде **своего** приложения регистрируйте доверенный обработчик и определение
расписания (например, в явной management-команде развёртывания, не в
`AppConfig.ready()`):

```python
from datetime import datetime, timezone

from apps.tasks.scheduler import register_schedule

register_schedule(
    name="nightly-report",
    code="reports.generate",
    payload={"report": "summary"},
    namespace="default",
    timezone_name="Asia/Almaty",
    hour=2,
    minute=30,
    weekdays=[0, 1, 2, 3, 4],  # Пн–Пт; [] — ежедневно
    max_attempts=5,
    start_at=datetime.now(timezone.utc),
)
```

`reports.generate` должен быть в `BACKGROUND_JOB_HANDLERS`.
Вторичная регистрация идентичного расписания возвращает ту же запись,
**не сбрасывая** `next_run_at`. Изменение конфигурации тем же именем
возвращает ошибку: ревизию расписания и сохранённые задания владелец
клиентского проекта должен мигрировать/обновлять осознанно. Приостановка
через `JobSchedule.is_enabled=False`; повторное включение приводит к
одному запуску за пропущенный период.

Сначала создайте и **закоммитьте в клиентском проекте** новую миграцию
`tasks` (`makemigrations tasks`, затем `migrate`), затем запустите
планировщик и уже существующие worker как отдельные процессы:

```bash
uv run python manage.py run_schedule_dispatcher
uv run python manage.py run_schedule_dispatcher --once
uv run python manage.py run_schedule_dispatcher --batch-size 100 --poll-seconds 10
uv run python manage.py run_background_jobs --lease-seconds 900
```

**Гарантии:**

- В PostgreSQL одна активная транзакция scheduler держит
  `pg_try_advisory_xact_lock`. Не получивший lock экземпляр не делает
  ничего. `SELECT FOR UPDATE SKIP LOCKED` защищает выбранные строки;
  вставка job и перенос `next_run_at` коммитятся **вместе**. Crash до
  commit не оставит потерянного запуска; после commit job восстановит
  существующий worker. SQLite допускается лишь для unit-тестов и не
  обеспечивает распределённую координацию.
- Каждое срабатывание имеет `idempotency_key`, вычисленный из UUID
  расписания и UTC-времени запуска. Уникальность
  `(namespace, idempotency_key)` на `BackgroundJob` не допускает
  дублирования *постановки* задания. Внешний side effect
  по-прежнему **at least once**: обработчик сам обеспечивает
  дедупликацию и таймаут.
- Это **локальное wall-clock расписание** (час:минута и необязательные
  дни недели) с IANA timezone. В весеннем DST gap несуществующее время
  пропускается, в осеннем fold запускается только **первое** вхождение.
  Следующий запуск хранится как aware UTC. Требуется установленная
  системная IANA timezone database (на некоторых Windows окружениях —
  пакет `tzdata`). При обновлении tzdb пересчитайте будущие курсоры
  при необходимости в клиентском проекте.
- **Misfire policy — coalesce:** после долгого простоя создаётся ровно
  один job за самый старый просроченный запуск каждого расписания;
  прочие пропущенные вхождения не воспроизводятся. Очередные даты
  вычисляются строго после текущего времени. Пакет ограничен
  `--batch-size`, чтобы избежать неограниченного backlog.
- Повторы/задержка, `max_attempts`, dead-letter состояние `failed`,
  recovery по `lease_seconds` и token fencing предоставляются
  **существующим** worker. Старый token не может завершить
  повторно захваченное задание. Для долгих задач увеличивайте lease
  относительно максимального времени выполнения; fencing статуса не
  предотвращает двойной side effect во внешнем API.

Нет произвольного cron-expression, catch-up всех пропущенных циклов,
автоматического продления worker lease или exactly-once исполнения.
Следите за возрастом `next_run_at`, числом `failed` и временем
работы обработчиков; масштабируйте worker независимо от scheduler.

## Transactional Outbox

Для durable business events выбирайте `--apps outbox`; он подключит `tasks` и использует существующую очередь с обязательной записью внутри транзакции. См. [Outbox](outbox-architecture.md).

## Дальнейшая кастомизация

Клиент может заменить этот контекст целиком на Celery, Django Tasks с поддерживаемым backend или собственную очередь. От PrimaryKit в runtime нет никаких зависимостей. Не меняйте существующую историю миграций при переходе: нужен новый план данных и cutover.
