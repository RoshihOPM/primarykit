# PrimaryKit — agent instructions

PrimaryKit is a copy-based Django starter, not a separately deployed shared backend. This file applies to repository changes and must be copied into each generated client repo with project-specific overrides.

## Required workflow

1. Read `README.md`, `docs/architecture.md`, and relevant existing app code before modifying behavior.
2. For new features, write an implementation plan with boundaries, API contract, failure modes, and tests. Keep small CRUD work proportional.
3. Write tests for behavior and edge cases before or together with implementation. Do not claim tests passed without running them.
4. Apply changes in a branch; never silently change production resources or merge into main.
5. Run: `uv sync --locked --all-groups`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run python manage.py check --settings=config.settings.test`, and `uv run pytest`.
6. For DB changes, run PostgreSQL integration tests and review migrations in a *generated client project*. Never regenerate or reset existing client migration histories.
7. Review for authorization/IDOR, validation, secrets, race conditions, N+1, query plans, transaction boundaries, and backwards compatibility.
8. If checks fail, fix the cause and rerun until green; disclose failures not reproducible locally.

## Applicable skills

- Architecture, system boundaries or API design: `.agents/skills/system-architect/SKILL.md`
- Models, SQL, indexes, transactions, schema changes: `.agents/skills/database-architect/SKILL.md`
- Any non-trivial feature implementation: `.agents/skills/feature-delivery/SKILL.md`

## Engineering conventions

- `config/` is the Django project; `apps/core/` is reusable cross-cutting code.
- Business apps expose their own serializers, services, selectors, permissions, urls and tests as needed.
- Don't introduce a CRUD abstraction when DRF ModelViewSet/serializer/model already suffice.
- Keep modules independent of client-specific business entities. Avoid generic `utils` dumping grounds.
- SOLID / KISS / DRY / YAGNI guide trade-offs; avoid speculative frameworks, needless service wrappers and premature microservices.
- All mutations affecting money, balances, stock or authorization require transaction and concurrency analysis.
- Do not put migrations in the reusable **catalog**. Each generated client repo MUST version its own migrations.
- Never copy third-party agent instructions or execute remote scripts without license/security review.
- Agents may perform independent code/DB reviews in parallel **only when supported by the active runtime**. Changes to the same files must be coordinated; a PR is the final integration gate.
- Never apply production migrations, modify production data, rotate secrets, or deploy without explicit approval.
