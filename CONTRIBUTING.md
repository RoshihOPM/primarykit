# Contributing to PrimaryKit / Участие в разработке

[English](#english) · [Русский](#русский) · [Code of Conduct](CODE_OF_CONDUCT.md) · [Security Policy](SECURITY.md)

## English

PrimaryKit is a **source-copy Django project generator**. Contributions must respect the ownership of independent generated client repositories, their migrations, APIs and business rules.

### Before opening an issue

Search existing issues and PRs to avoid duplicates. Use [Bug Report](.github/ISSUE_TEMPLATE/bug_report.yml) for reproducible defects and [Feature Request](.github/ISSUE_TEMPLATE/feature_request.yml) for proposals. Include a concrete problem, module scope and acceptance criteria. **Security vulnerabilities must follow [SECURITY.md](SECURITY.md), never a public bug report.**

For complex modules or changed public contracts, propose boundaries, dependencies, failure modes, API shapes, migration effects and a test plan before implementing.

### Preparing a change

1. Fork or branch from the latest `main`. Keep one coherent change per PR; prefer `fix/<topic>`, `feat/<topic>`, `docs/<topic>`.
2. Read [AGENTS.md](AGENTS.md), [architecture](docs/en/architecture.md), the relevant [module guide](docs/en/modules.md), ADR and code/tests.
3. Keep business rules in the correct bounded context. Don't introduce upstream PrimaryKit runtime imports into generated clients. Modules declare requirements in `manifest.py`; optional integrations must fail closed when unavailable.
4. **Do not edit source-catalog migration history.** New clients generate, review and version their own migrations. Existing client migrations are changed only via reviewed additive changes.
5. Add regression tests, including anonymous/cross-owner/cross-tenant, role elevation, invalid transitions, stale writes and PostgreSQL races when applicable. Validate a **detached generated project** for generator/module changes.
6. Update the English and Russian README/index/module documentation when interfaces or behavior change. Describe backwards compatibility and deployment changes.

### Local verification

Requires Python 3.13, uv and the documented database setup.

```bash
uv sync --locked --all-groups
uv run python -m apps.core.doctor --strict
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check --settings=config.settings.test
uv run pytest
```

For database changes also run the corresponding PostgreSQL integration test and smoke-check a generated client with **client-owned migrations**. The CI workflow runs broader generator, Docker and optional infrastructure checks. Do not state that tests passed unless they were actually executed.

### PR checklist and review

Use the [pull request template](.github/PULL_REQUEST_TEMPLATE.md). Explain motivation, design trade-offs, changed routes/permissions/settings, test commands/results, schema migration and rollout, risks and documentation. PRs containing production secrets, customer records or third-party code of uncertain provenance will not be accepted. Never force-push or merge into `main` outside the repository's review/protection policy.

CI green is required; maintainers may request additional security, migration or backwards-compatibility review. A contributor must not treat their own approval as independent review. A single-maintainer repository may initially use required PR + CI without mandatory external approval until a qualified reviewer has repository access.

### Licensing and provenance

The project uses [MIT License](LICENSE). By contributing you confirm you have the right to submit your work under MIT and that it does not contain improperly copied third-party/client-owned code. Preserve pre-existing copyright and license notices. No contributor license agreement or DCO sign-off mechanism is currently required. Generated client applications can have separately licensed **new client code**, while redistributed substantial portions of PrimaryKit retain its MIT notices.

## Русский

PrimaryKit — **конструктор независимых Django backend-проектов с копированием исходников**. Правила и миграции созданных клиентских репозиториев остаются под контролем этих проектов.

### Перед работой

Проверьте существующие Issues/PR. Для воспроизводимого бага используйте [Bug Report](.github/ISSUE_TEMPLATE/bug_report.yml), для предложения — [Feature Request](.github/ISSUE_TEMPLATE/feature_request.yml). Не публикуйте уязвимости в Issue: соблюдайте [SECURITY.md](SECURITY.md). Для больших изменений заранее опишите контекст, API, инварианты, миграции и тесты.

### Порядок разработки

1. Создайте отдельную ветку от актуального `main` и ограничьте PR одной задачей.
2. Изучите [AGENTS.md](AGENTS.md), [архитектуру](docs/architecture.md), [каталог модулей](docs/modules.md), ADR и имеющиеся тесты.
3. Сохраняйте чистые доменные границы и независимость клиентских копий; зависимости объявляйте через `manifest.py`.
4. Миграции принадлежат сгенерированным клиентам. Не сбрасывайте существующую историю и не подменяйте schema review автогенерацией в продакшене.
5. Добавьте регрессионные тесты, негативные проверки прав/IDOR и PostgreSQL concurrency tests, где затронуты защищённые данные, деньги, статусы или транзакции. Тестируйте автономный сгенерированный проект.
6. Синхронизируйте RU/EN документацию, включая README, индексы и контракты модулей.

### Обязательные проверки

```bash
uv sync --locked --all-groups
uv run python -m apps.core.doctor --strict
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check --settings=config.settings.test
uv run pytest
```

Для изменения моделей проверяйте реальные PostgreSQL-транзакции и миграции клиента. В описании PR укажите реально выполненные проверки, компромиссы, риски, влияние на API и rollout. CI и review обязательны перед слиянием. Нельзя коммитить клиентские данные, секреты или сторонний код с непроверенными правами.

### Лицензирование

Код PrimaryKit распространяется по [MIT](LICENSE). Отправляя вклад, вы подтверждаете право предоставить его на этих условиях. Сохраняйте уведомления об авторских правах; собственные дополнения клиента могут лицензироваться отдельно. CLA или обязательный DCO sign-off пока не применяются.

Следуйте [Кодексу поведения](CODE_OF_CONDUCT.md) и [политике безопасности](SECURITY.md).
