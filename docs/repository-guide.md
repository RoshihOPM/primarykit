# Как устроен PrimaryKit

## Зачем создан проект

При разработке новых Django backend-проектов часто повторяются регистрация, роли, файлы, каталог, склад, заказы, уведомления и инфраструктура. PrimaryKit хранит эти функции как **проверенные переносимые папки исходного кода** с едиными соглашениями.

Типичный сценарий: выбрать требуемые компоненты, создать чистый backend, доработать его под клиента, хранить собственные миграции и деплоить независимо от PrimaryKit. Изменения конструктора не обновляют автоматически клиентские проекты.

## Структура

```text
primarykit/
├── apps/
│   ├── core/             # registry, base models, health, install command
│   ├── users/            # custom User + authentication
│   ├── notifications/    # email rendering/delivery
│   ├── organizations/    # tenants and memberships
│   ├── catalog/          # standalone / tenant schema
│   ├── inventory/        # standalone / tenant schema
│   ├── orders/           # priced order snapshots
│   ├── sales/            # sales ledger
│   ├── payments/         # payment intents and manual reconciliation
│   ├── statistics/       # plugin-based metric queries
│   └── ...               # storage, audit, rbac
├── config/
│   ├── settings/         # base, local, test, postgres_test, production
│   └── urls.py           # routes discovered from app manifests
├── scripts/new_project.py  # standalone backend generator
├── docs/                   # manuals and architecture decisions
├── .agents/skills/         # guidelines for coding agents
├── .github/workflows/      # CI
├── docker/                  # dev/prod Docker targets
├── compose*.yaml
├── pyproject.toml
└── uv.lock
```

## Договор модуля

В каждой `apps/<name>/` нужен `manifest.py`, который экспортирует `MODULE = Module(...)`: имя, `requires`, `optional`, `routes`, `priority`. При запуске конфигурация сама добавляет существующие приложения в `INSTALLED_APPS`, а маршруты — в `urlpatterns`. Если обязательный модуль отсутствует, запуск остановится с понятной ошибкой. Папка `statistics.py` опционально предоставляет метрики.

Как минимум модель/сервис/API/тесты и короткая документация для нетривиального модуля. Усложнять простые CRUD пустыми слоями не требуется.

## Архитектурные границы

Бизнес-код находится в собственном Django app — bounded context. `domain.py` должен оставаться чистым Python: правила, переходы состояний, деньги и ограничения; `services.py` управляет транзакциями, ORM, идемпотентностью и необязательными интеграциями; DRF views/serializers — транспортные адаптеры.

Все клиентские запросы должны быть ограничены владельцем/организацией не только в `get_queryset`, но и в вызываемом сервисе. Никакого tenant-bypass через глобальный `is_superuser`. Изменения, где это необходимо, выполняются через `transaction.atomic` и `select_for_update` с единым порядком блокировок.

Другие контексты связываются через свои публичные сервисы или явные opaque IDs с повторной авторизацией, а не через прямые импорты views. `Orders/Sales/Payments` используют именно такой подход. `Catalog/Inventory` сохраняют два заранее выбранных варианта моделей из соображений совместимости.

## Почему это не pip-библиотека

После копирования проект владеет кодом. Можно менять бизнес-правила и миграции без обновления всех проектов клиентов. Плата за это — обновления между клиентами выполняются явно, через PR/review, а не автоматически.

## Что генератор делает и чего не делает

**Делает:** копирует выбранные приложения и обязательную основу, вычисляет closure зависимостей, фиксирует режим Catalog/Inventory, формирует независимый `pyproject.toml` и `uv.lock`, может выполнить `git init`, оставляет metadata `primarykit-origin.json`.

**Не делает:** создавать миграции за тебя в продакшене, покупать домен, настраивать nginx/HTTPS, provision storage/SMTP, автоматически переписывать существующую клиентскую базу, синхронизировать продажи со складом или принимать реальные платежи.

## Что изучать дальше

[Quickstart](getting-started.md) → [Каталог модулей](modules.md) → [Написать модуль](module-development.md) → [Deploy](deployment.md).

Глубокие решения описаны в [ADR 0001](adr/0001-copy-based-modular-monolith.md), [0003](adr/0003-implemented-ddd-boundaries.md), [0004](adr/0004-copyable-module-contract.md), [0005](adr/0005-standalone-catalog-inventory.md).
