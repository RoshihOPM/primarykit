# Workflows — переносимый автомат состояний

Модуль `apps/workflows` предоставляет **чистые Python-правила**, Django-адаптер
конкурентных изменений и **необязательный** журнал переходов. Нет публичного
HTTP API, связи с Orders/Organizations/RBAC и обязательного брокера.

## Границы и владение данными

- Клиент определяет состояния, команды, разрешения и guards в `WorkflowDefinition`.
- Клиентский aggregate **сам владеет** `workflow_state` и `workflow_version`.
  Можно наследоваться от абстрактного `WorkflowStateMixin` или передать свои
  `state_field` / `version_field` в `advance`.
- Клиент выбирает scoped QuerySet **и** обязательный `authorize(actor, aggregate)`.
  Обе проверки нужны, в том числе при вызове сервиса из фонового обработчика.
  Системный суперпользователь не получает доступ автоматически.
- `scope` задаётся **доверенным кодом** клиента, например
  `orders:tenant_<organization_uuid>`, а не напрямую из HTTP.
  Идентичность события строится из `scope`, `aggregate.pk` и следующей версии.
- Модуль не создаёт модель заказа, роли, URL, конфигурацию чужих переходов
  или relation на произвольную клиентскую таблицу.

## Сценарий интеграции

В новом клиенте определите workflow рядом со своим доменом (ниже пример;
`approved` — терминальное состояние).

```python
from apps.workflows.domain import TransitionRule, WorkflowDefinition

ORDER_FLOW = WorkflowDefinition(
    states=frozenset({"draft", "approved", "rejected"}),
    initial="draft",
    terminal=frozenset({"approved", "rejected"}),
    transitions=(
        TransitionRule(
            "draft", "approve", "approved",
            permission=lambda ctx: ctx.actor.can_approve_orders,
            guard=lambda ctx: ctx.aggregate.total_is_valid,
        ),
        TransitionRule("draft", "reject", "rejected"),
    ),
)
```

Создайте client-owned aggregate с начальным состоянием `draft`, версией 0.
При выполнении команды вызывайте:

```python
from apps.workflows.services import advance

event = advance(
    definition=ORDER_FLOW,
    queryset=Order.objects.filter(organization_id=trusted_organization_id),
    pk=order_id,
    expected_version=expected_version,
    action="approve",
    scope=f"orders:tenant_{trusted_organization_id}",
    actor=request.user,
    authorize=lambda actor, order: order.organization.can_manage_orders(actor),
    record_history=True,
)
```

Метод возвращает неизменяемый `TransitionEvent` с детерминированным
`event_id`, `scope`, `aggregate_id`, `action`, `from_state`, `to_state`
и новым `version`.

## Атомарность и ошибки

В одной `transaction.atomic(using=queryset.db)`:

1. Выполняется `select_for_update()` по scoped QuerySet.
2. Под row lock повторно проверяется разрешение, `expected_version`,
   допустимый переход, пермишен и guard.
3. Один conditional `UPDATE` сравнивает **предыдущее состояние и версию**.
   При нуле обновлённых строк возвращается `StaleTransition`.
4. По флагу `record_history=True` записывается `WorkflowTransitionHistory`
   с уникальной тройкой (`scope`, `aggregate_id`, `version`).
5. По желанию вызывается `audit_hook(event)` внутри той же транзакции
   (только DB effects; исключение откатывает и state, и history).

Повторное выполнение команды со старой версией отклоняется. Доменные ошибки:
`InvalidTransition`, `WorkflowPermissionDenied`, `GuardRejected`,
`StaleTransition`; некорректная конфигурация отклоняется сразу.

**Важно:** row-level locking гарантирован на PostgreSQL, но не на SQLite.
Conditional UPDATE — дополнительная защита от потери обновлений; интеграционный
тест двух конкурентных исполнителей запускается на PostgreSQL. Не отправляйте
email или network calls внутри `audit_hook`: для доставки с повторами
используйте опциональный Outbox из той же транзакции, а получателей делайте
идемпотентными по `event_id`. Создание истории не публикует событие само.

## Данные, безопасность и жизненный цикл

- `WorkflowTransitionHistory` — журнал для доверенного клиентского кода;
  endpoint для его чтения не предоставляется. Чтение **обязательно**
  фильтровать теми же агрегатными tenant/owner-проверками, что и команду.
- Журнал не содержит actor, raw metadata или чувствительных данных. Для
  дополнительной информации используйте собственную аудируемую таблицу
  и политику retention, учитывая приватность и удаление агрегата.
- `record_history=False` по умолчанию; поля state/version хранятся
  непосредственно в модели клиента вне зависимости от журнала.
- Aggregate может быть удалён клиентом; тогда клиент ответственен за
  хранение/очистку осиротевшей истории и политику retention.
- Бизнес-guards должны быть чистыми: без сетевых операций и побочных эффектов.
  Если guard зависит от других изменяемых строк, клиент должен захватить
  подходящие lock-строки в фиксированном порядке внутри той же транзакции.
- Сигналы Django `save()` на агрегате **не вызываются**, так как используется
  conditional `QuerySet.update()`; для side effects используйте audit/outbox.
- История immutable **на уровне сервиса**, но Django ORM не запрещает
  прямой `update()/delete()`; ограничьте административный DB-доступ.

## Генерация и миграции

```bash
uv run python scripts/new_project.py ../workflow-client --name workflow-client --apps workflows
cd ../workflow-client
uv run python manage.py makemigrations users workflows
uv run python manage.py migrate
uv run python -m apps.core.doctor --strict
uv run pytest -q apps/workflows
```

Миграции **принадлежат клиенту** и должны быть сохранены в его Git. Вносите
изменения в схему через отдельные новые миграции, не пересоздавайте историю.
Модуль требует только `core`; `audit` и `outbox` — необязательные адаптеры.
