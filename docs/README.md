# Документация PrimaryKit

Это оглавление для разработчика, который впервые открыл репозиторий.

## Начните отсюда

1. **[Что такое PrimaryKit и как устроен репозиторий](repository-guide.md)** — границы системы, структура каталогов, что является модулем, что копируется.
2. **[Quickstart: установка и первый запрос](getting-started.md)** — от `git clone` до работающего API и миграций.
3. **[Все модули и их зависимости](modules.md)** — таблица самостоятельности, маршруты, вариант с организациями.
4. **[Генератор независимых проектов](project-generator.md)** — CLI, выбор набора, копирование, `primarykit-origin.json`.
5. **[Как написать свой модуль](module-development.md)** — файлы, manifest, модели, API, сервисы, тесты и интеграции.
6. **[Orders, Sales и Payments](commerce-architecture.md)** — жизненный цикл, деньги, схема API, что НЕ делает платежный модуль.
7. **[Statistics](statistics-architecture.md)** — единый API и подключение своих метрик.
8. **[Развёртывание и поддержка](deployment.md)** — Docker, Linux/Nginx, SSL, PostgreSQL, бэкапы.

## Подробные документы

- [Core conventions](core-conventions.md) · [Users](users-architecture.md) · [Notifications](email-notifications.md)
- [Organizations](organizations-architecture.md) · [RBAC](rbac-architecture.md) · [Audit](audit-architecture.md)
- [Catalog](catalog-architecture.md) · [Inventory](inventory-architecture.md) · [Storage](storage-architecture.md)
- [Architecture](architecture.md) · [Agent workflow](agent-workflow.md) · [Module roadmap](module-roadmap.md)

## Архитектурные решения

- [ADR 0001](adr/0001-copy-based-modular-monolith.md): копирование исходников вместо общей runtime-библиотеки.
- [ADR 0002](adr/0002-storage-bounded-context-and-policies.md): личные/корпоративные файлы и доступ.
- [ADR 0003](adr/0003-implemented-ddd-boundaries.md): чистые доменные правила.
- [ADR 0004](adr/0004-copyable-module-contract.md): manifest и копирование модулей.
- [ADR 0005](adr/0005-standalone-catalog-inventory.md): два режима Catalog и Inventory.
- [Commerce Architecture](commerce-architecture.md): отдельные Orders, Sales, Payments и политика платежей.

## Для контрибьюторов и агентов

Прочитайте [AGENTS.md](../AGENTS.md), [tests and review gates](module-development.md) и [agent workflow](agent-workflow.md). Изменения должны проходить Ruff, pytest, генератор и CI; PR объединяется с main только при успешных проверках.
