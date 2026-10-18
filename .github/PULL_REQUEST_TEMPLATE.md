## Summary / Изменения

<!-- Why this change is necessary, what is in scope and what is intentionally out of scope. -->

## Architecture and compatibility / Архитектура и совместимость

- [ ] Module boundaries and `manifest.py` dependencies reviewed (if applicable)
- [ ] Existing routes / permissions / schemas / settings documented
- [ ] Owner / tenant scope and privilege boundaries checked
- [ ] No new runtime dependency from generated clients to PrimaryKit
- [ ] Generated-client migration policy preserved

## Verification / Проверки

<!-- State actual results, not assumptions. Mark unchecked if not run. -->

- [ ] `uv sync --locked --all-groups`
- [ ] `uv run python -m apps.core.doctor --strict`
- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run python manage.py check --settings=config.settings.test`
- [ ] `uv run pytest`
- [ ] Detached generated-client smoke (for module/generator changes)
- [ ] PostgreSQL transaction/IDOR/concurrency tests (if sensitive or DB-related)
- [ ] Security review for auth, tenant, uploads, money or PII (if applicable)

## Rollout and risks / Риски и внедрение

<!-- Migration plan, failure modes, backwards compatibility, rollback, or N/A. -->

## Documentation, privacy and license / Документация и лицензия

- [ ] Relevant RU and EN documentation synchronized (or N/A explained)
- [ ] No secrets, production/client data, third-party code without rights
- [ ] Copyright / MIT notices retained for derived PrimaryKit code
- [ ] CI completed successfully before merge

Related issues:
