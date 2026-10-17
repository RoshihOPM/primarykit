# Privacy retention — клиентские политики персональных данных

`apps/privacy` — опциональный оркестратор **явных** действий `redact`, `anonymize`, `delete`, а не универсальный механизм физического удаления. Он **не знает** моделей конкретного клиента, не вызывает `QuerySet.delete()` автоматически и никогда не удаляет каскадом финансовые записи.

## Независимая установка

```bash
uv run python scripts/new_project.py ../privacy-api --name privacy-api --apps privacy
cd ../privacy-api
uv run python manage.py makemigrations users audit tasks privacy
uv run python manage.py migrate
```

Обязательные зависимости подключаются автоматически: `audit` и PostgreSQL-backed `tasks`. Каждое сгенерированное приложение владеет **своими** миграциями и политиками. У существующих клиентов допускаются только новые review-approved migrations, не сброс истории.

## Настройка в собственном проекте

В доверенных настройках приложения:

```python
PRIVACY_RETENTION_POLICIES = {
    "customer_contact": {
        "kind": "customer",
        "actions": ("redact", "anonymize"),  # delete запрещен
        "grace_days": 7,
        "handler": "apps.customers.privacy.redact_customer",
    },
}
PRIVACY_AUTO_EXECUTION_ENABLED = False  # безопасное значение по умолчанию
# При установке через генератор Tasks уже содержит:
BACKGROUND_JOB_HANDLERS["privacy.execute"] = "apps.privacy.services.process_retention_job"
```

Каждая политика явная: разрешенные операции, subject kind, период ожидания от 0 до 3650 дней и доверенный путь к handler, выбранный **разработчиком клиента**. У каждой организации могут быть собственные scope и отдельные политики в клиентском коде, но сам `scope` не предоставляет права доступа.

Handler вызывается с `(*, scope: str, kind: str, subject_id: UUID, action: str)` и **обязан**:
- обрабатывать только свои локальные записи и конкретные разрешенные поля;
- оставлять обязательные финансовые документы, историю расчетов и другие записи, требуемые законом;
- быть идемпотентным и выполнять только транзакционные ORM-изменения;
- не отправлять HTTP, SMTP, S3-delete и другие необратимые внешние side effects прямо из транзакции.

Для внешних действий нужен отдельный Outbox и идемпотентный consumer, а для backups/логов — самостоятельная политика хранения. Формальная оценка GDPR/локальных законов остается обязанностью клиента.

## Внутренний API сервисного слоя

```python
from uuid import uuid4
from apps.privacy.services import (
    preview,
    request_retention,
    execute_manually,
    set_legal_hold,
    release_legal_hold,
    cancel_request,
)

plan = preview(
    scope="client:one",
    kind="customer",
    subject_id=customer.id,
    policy_code="customer_contact",
    action="redact",
    actor=admin,
)
operation = request_retention(
    scope="client:one",
    kind="customer",
    subject_id=customer.id,
    policy_code="customer_contact",
    action="redact",
    idempotency_key=uuid4(),
    actor=admin,
)
execute_manually(request_id=operation.id, actor=admin)
set_legal_hold(
    scope="client:one", kind="customer", subject_id=customer.id, reason="legal", actor=admin
)
release_legal_hold(scope="client:one", kind="customer", subject_id=customer.id, actor=admin)
cancel_request(request_id=operation.id, actor=admin)
```

Все административные команды проверяют **активного суперпользователя** внутри services. HTTP endpoint модулем **не предоставляется**; при создании клиентского API обязательно вводите собственное подтверждение личности, object-level authorization и rate limiting. `subject_id` и `idempotency_key` — непрозрачные UUID (никаких email или имен). Причина legal hold — только код `legal`, `regulatory` или `dispute`; не кладите PII в текст причины.

`preview()` и `request_retention(..., dry_run=True)` ничего не изменяют в БД и не вызывают обработчики. План показывает grace deadline, активность hold и настройку фонового исполнения. Создание запроса при выключенной автоматизации оставляет его в статусе `pending`, для исполнения нужна явная команда администратора после истечения grace window.

Для автоматической обработки **новых** запросов после review клиент осознанно устанавливает `PRIVACY_AUTO_EXECUTION_ENABLED=True` и запускает отдельный `run_background_jobs` worker. Если отключить флаг после постановки задания, worker **откажет** в автоматическом выполнении и Tasks применит retries/failed. Существующие ручные заявки сами не начнут удаляться при включении флага. Требуется ручной разбор.

## Согласованность и правовые блокировки

- На один `(scope, kind, subject_id)` возможна одна активная операция. `PrivacyRequest.idempotency_key` глобально уникален; повтор возвращает прежний запрос только при совпадении политики и операции.
- При переходах `requested`, `held`, `released`, `cancelled`, `completed` записываются события Audit в одной DB-транзакции. В Audit хранятся UUID запроса и код политики, **никогда** старое/новое содержимое персональных полей.
- Правовой запрет хранится у `PrivacySubject`, применяется и к будущим запросам. Все конкурентные изменения захватывают row-lock `PrivacySubject`, затем `PrivacyRequest`. Действие повторно проверяет hold, срок, статус и подписанный SHA-256 fingerprint политики прямо перед handler.
- При изменении разрешенных операций, grace или handler старый запрос останавливается и требует ручного согласования новой заявки.
- Tasks доставляет события **at least once**. `revision` предотвращает выполнение старых задач после hold/release/cancel. Если обработчик падает, его ORM-изменения и завершение запроса откатываются вместе. Неоткатываемые side effects недопустимы.
- `delete` не включен ни для одной политики по умолчанию. Его реальная семантика — полностью клиентская, без cascade из этого модуля.

## Rollout, мониторинг, rollback

До включения автоматизации нужно протестировать handler на обезличенной копии реальных данных, провести юридический review обязательных retention-сроков, выполнить PostgreSQL race tests и проверить план миграций/резервных копий. Следите за `tasks.BackgroundJob.failed`, задержкой очереди и зависшими `privacy.PrivacyRequest.pending`. SQLite unit tests не проверяют межпроцессные блокировки.

При проблеме выключите флаг автоисполнения и остановите worker. Сохраните таблицы `privacy` и `audit` для расследования. Выполненная анонимизация необратима без резервной копии и не должна считаться автоматически откатываемой.
