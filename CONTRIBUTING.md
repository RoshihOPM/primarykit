# Contributing / Участие в разработке

[English](#english) · [Русский](#русский)

## English

Thank you for helping improve PrimaryKit. Please read [AGENTS.md](AGENTS.md), the [architecture guide](docs/en/architecture.md), [module catalog](docs/en/modules.md) and any affected module references before proposing changes.

1. Open a focused issue/PR with motivation, scope, API/manifest/migration compatibility implications and alternatives.
2. Implement a module as a reusable **copyable source folder**, not a dependency on a globally installed PrimaryKit runtime.
3. Preserve the independence of generated repositories; never silently update client-owned source or migration histories.
4. Add behavior, negative authorization and PostgreSQL concurrency tests for affected sensitive paths; generated-client smoke tests are required for module changes.
5. Run `uv sync --locked --all-groups`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run python manage.py check --settings=config.settings.test`, `uv run pytest`.
6. Keep English and Russian entry documentation consistent with new user-visible behavior. Update `README.md`, `README.ru.md`, the two documentation indexes, English module overview and the detailed module reference as appropriate.
7. Submit a PR. Do not merge until CI and review pass. Never include production data, private secrets, proprietary client code or material whose redistribution rights are unclear.

Before public contribution workflows are enabled, the repository owner must choose and commit an explicit source license. This document does not grant additional licensing rights.

## Русский

Перед изменениями изучите [AGENTS.md](AGENTS.md), [архитектуру](docs/architecture.md), [каталог модулей](docs/modules.md) и документацию затрагиваемого контекста.

1. Создавайте узкий Issue/PR с целью, границами и влиянием на API, manifest и миграции.
2. Сохраняйте принцип **переносимого исходника** — не вводите runtime-зависимость созданных клиентов от PrimaryKit.
3. Не обновляйте автоматически клиентские репозитории и их историю миграций.
4. Для защищённых операций добавляйте негативные тесты прав и PostgreSQL concurrency; для модулей — smoke на сгенерированном проекте.
5. Выполняйте `uv sync --locked --all-groups`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run python manage.py check --settings=config.settings.test`, `uv run pytest`.
6. Синхронизируйте английский/русский README, два индекса, общий каталог и подробные документы по изменённому поведению.
7. Открывайте PR и проверяйте CI перед слиянием. Не переносите секреты, приватные данные и сторонний код без прав на распространение.

Выбор лицензии остаётся за владельцем. Сам этот файл не предоставляет новых прав на использование кода.
