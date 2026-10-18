# Документация PrimaryKit

**Язык:** Русский · [English](en/README.md) · [Главная](../README.ru.md)

Документация актуализирована под реализованные модули в `main` на 18 октября 2026 года. PrimaryKit — исходный каталог и генератор **независимых Django backend-проектов**; миграции и бизнес-правила принадлежат созданному клиентскому проекту.

## Быстрый маршрут

1. [Установка и первый запуск](getting-started.md)
2. [Каталог 31 модуля, зависимости, API](modules.md)
3. [Архитектура](architecture.md) · [Независимость проектов](independent-projects.md)
4. [Генератор и пресеты](project-generator.md) · [Добавление модулей](module-development.md) · [Scaffold и граф зависимостей](module-scaffold.md)
5. [Проверка проекта (Doctor)](doctor.md) · [Совместимость модулей](module-compatibility.md) · [Проверка обновлений](module-upgrades.md) · [OpenAPI diff](api-compatibility.md)
6. [Текущее состояние и ограничения](project-status.md) · [Roadmap](module-roadmap.md)
7. [Деплой](deployment.md) · [Production runbook](production-operations.md)

## Справочник по контекстам

| Категория | Документы |
| --- | --- |
| Identity и права | [Users](users-architecture.md), [Device Sessions](device-sessions.md), [Organizations](organizations-architecture.md), [RBAC](rbac-architecture.md), [API Keys](api-keys.md), [Audit](audit-architecture.md) |
| Бизнес | [Catalog](catalog-architecture.md), [Inventory](inventory-architecture.md), [Orders/Sales/Payments](commerce-architecture.md), [Statistics](statistics-architecture.md), [Storage](storage-architecture.md) |
| Команды и данные | [Workflows](workflows.md), [Usage Quotas](usage-quotas.md), [Privacy Retention](privacy-retention.md), [Idempotency](idempotency.md), [CSV](csv-exchange.md), [Search](search.md) |
| Асинхронная доставка | [Tasks + Scheduler](tasks-architecture.md), [Outbox](outbox-architecture.md), [Webhooks](webhooks.md), [Celery/RabbitMQ](celery-rabbitmq.md) |
| Интеграции и эксплуатация | [Chat/Realtime](chat-realtime.md), [Redis Cache](redis-cache.md), [Rate Limiting](rate-limiting.md), [Observability](observability.md), [Notifications](email-notifications.md), [Feature Flags](feature-flags.md), [HTTPS integrations](http-integrations.md) |
| Архитектура и разработка | [Repository guide](repository-guide.md), [Core conventions](core-conventions.md), [Architecture recipes](architecture-recipes.md), [Agent workflow](agent-workflow.md) |

Дополнительно: [Лицензия MIT](../LICENSE), [Безопасность](../SECURITY.md), [Участие](../CONTRIBUTING.md), [Кодекс поведения](../CODE_OF_CONDUCT.md), [Поддержка и защита main](maintainer-playbook.md).

## Архитектурные решения

[ADR 0001](adr/0001-copy-based-modular-monolith.md) · [ADR 0002](adr/0002-storage-bounded-context-and-policies.md) · [ADR 0003](adr/0003-implemented-ddd-boundaries.md) · [ADR 0004](adr/0004-copyable-module-contract.md) · [ADR 0005](adr/0005-standalone-catalog-inventory.md).

Перед PR прочитайте [AGENTS.md](../AGENTS.md). Тесты, проверки безопасности и миграции сгенерированных клиентов обязательны для соответствующих изменений.

- [AI-assisted development](ai-assisted-development.md) — как передавать независимый проект AI-агенту, без копирования ненужных модулей.

- [Объявления / Listings](listings.md) — объявления продавцов и модерация отдельно от Catalog.
