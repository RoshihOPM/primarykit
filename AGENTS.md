# PrimaryKit — agent instructions

PrimaryKit is a copy-based Django starter, not a separately deployed shared backend. This file applies to repository changes and must be copied into each generated client repo with project-specific overrides.

## Required workflow

1. Read `README.md`, `docs/architecture.md`, and relevant existing app code before modifying behavior.
2. For new features, write an implementation plan with boundaries, API contract, failure modes, and tests. Keep small CRUD work proportional.
3. Write tests for behavior and edge cases before or together with implementation. Do not claim tests passed without running them.
4. Apply changes in a branch; never silently change production resources or merge into main.
5. Run: `uv sync --locked --all-groups`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run python manage.py check --settings=config.settings.test`, and `uv run pytest`.
6. For DB changes, run PostgreSQL integration tests and review migrations in a *generated client project*. Never regenerate or reset existing client migration histories.
7. Apply security-review skill for API/auth changes; review authorization/IDOR, validation, secrets, race conditions, N+1, query plans, transaction boundaries, and backwards compatibility.
8. If checks fail, fix the cause and rerun until green; disclose failures not reproducible locally.

## Applicable skills

- Architecture, system boundaries or API design: `.agents/skills/system-architect/SKILL.md`
- Models, SQL, indexes, transactions, schema changes: `.agents/skills/database-architect/SKILL.md`
- Any non-trivial feature implementation: `.agents/skills/feature-delivery/SKILL.md`
- Every auth, API permission, user, wallet, tenant, payment, or sensitive-data feature: `.agents/skills/security-review/SKILL.md`

## Engineering conventions

- `config/` is the Django project; `apps/core/` is reusable cross-cutting code.
- Business apps expose their own serializers, services, selectors, permissions, urls and tests as needed.
- Follow ADR 0003: pure business decisions in `domain.py` (no Django/DRF/ORM or cross-context imports); existing `services.py` orchestrates transactions and domain rules. Django models, DRF views and external transports are adapters.
- Use explicit contracts between contexts. Never import another context's views or serializers into domain/application logic. Avoid empty DDD scaffold directories.
- For domain changes add pure tests and generated-project smoke; for mutations retain PostgreSQL concurrency, tenant IDOR and audit checks.
- Don't introduce a CRUD abstraction when DRF ModelViewSet/serializer/model already suffice.
- Keep modules independent of client-specific business entities. Avoid generic `utils` dumping grounds.
- SOLID / KISS / DRY / YAGNI guide trade-offs; avoid speculative frameworks, needless service wrappers and premature microservices.
- All mutations affecting money, balances, stock or authorization require transaction and concurrency analysis.
- Each tenant API must filter both list/detail querysets by membership, validate foreign keys from the same tenant, and deny implicit global Group privileges.
- Protect last active owner under a row lock; include negative IDOR and cross-branch tests.
- Catalog and Inventory have two pinned schema modes (ADR 0005). Tenant mode requires Organizations, and Inventory additionally requires Catalog. Standalone mode is owner-scoped and must reject other users in both DRF and services. Never expose tenant data via personal endpoints.
- Storage has separate personal and organization-scoped APIs. Organization access requires the optional Organizations policy adapter, and service commands recheck access. No global superuser tenant bypass.
- Do not put migrations in the reusable **catalog**. Each generated client repo MUST version its own migrations.
- Never copy third-party agent instructions or execute remote scripts without license/security review.
- Agents may perform independent code/DB reviews in parallel **only when supported by the active runtime**. Changes to the same files must be coordinated; a PR is the final integration gate.
- Never apply production migrations, modify production data, rotate secrets, or deploy without explicit approval.

## Independent generated-project policy

- **Copy, never runtime-depend.** A generated backend must build, test, run and deploy after the PrimaryKit source checkout is deleted. No imports from `primarykit`, `scripts.new_project`, shared APIs or runtime dependency on an upstream package.
- Client repositories own their business logic, versions, schema modes, migration history, secrets and release decisions. Sample Orders/Sales/Payments, Catalog/Inventory are not universal domain models.
- Do not introduce automatic updates or production migration of client-owned source. A source fix is propagated only by deliberate client-specific change/review/PR.
- Run `python -m apps.core.doctor --strict` inside generated backends, as well as the usual tests. The doctor does not need Django startup, network access or a kit checkout, and is only a static preflight; it does not replace ORM migrations or runtime security tests.
- See `docs/independent-projects.md`, `docs/doctor.md`, and `docs/architecture-recipes.md`.

## Rate limiting

- Public authentication/registration/password endpoints must enforce a shared store (Redis or trusted edge) for horizontally scaled deployments; Django's process-local cache cannot provide a global security boundary.
- `apps/rate_limit` is opt-in, requires cache, hashes client IPs into keys, never trusts inbound proxy headers, and fails closed when Redis is unavailable.

## Optional infrastructure modules

- `apps/cache` uses an independent redis-py CacheService as the default API (JSON, Hashes, counters). Django Cache and django-redis are optional bridges. Do not make Redis mandatory for generated clients. Redis is ephemeral and never authoritative for permissions or financial state.
- `apps/celery_tasks` is independent of the PostgreSQL `apps/tasks` queue. RabbitMQ broker and Redis result backend are opt-in. Business task handlers belong to each generated client; publish after commit and use an outbox for delivery guarantees when required.
- Select overlay Compose files explicitly; never expose Redis/RabbitMQ services to public interfaces or install optional broker dependencies into unrelated clients. See `docs/redis-cache.md` and `docs/celery-rabbitmq.md`.

## Portable module contract

- A module is discovered from `apps/<name>/manifest.py`, not manually added to `INSTALLED_APPS` or root URLs. Define hard dependencies, optional integrations, stable route prefixes and priority there. Add tests for the generator's dependency closure and for the standalone variant where applicable.
- Core/users/notifications are the minimum project baseline. Copying a module with required missing dependencies MUST fail at startup; the `install_kit_module` management command resolves closure from a **trusted** source checkout. Never silently import an optional context.
- Copying code does not apply migrations, provision the database or install third-party packages. Clients must generate/review/commit their own migrations; never auto-migrate production as an AppConfig side effect.
- Maintain isolation: an optional integration must fail closed when absent, especially tenant scoping and file access. Keep DDD domain rules framework-independent.

## Catalog and Inventory schema modes

- Independent `catalog` and `inventory` folders use pinned `CATALOG_MODE` / `INVENTORY_MODE` (`standalone` or `tenant`) selected before the first migration. Do not infer, flip or migrate modes in AppConfig.ready() or a registry import.
- Standalone Catalog and Inventory must remain free of imports from Organizations and Catalog (for Inventory), including at model import time. All owner scope checks are mandatory at both API and transactional command boundaries; no implicit Django superuser bypass.
- Tenant implementation remains a separate explicit adapter with original models, migrations and routes. Any mode conversion on a populated database needs an agreed and tested data migration, including historical immutable movements and idempotency partitions.

## Statistics provider security

- Optional `apps/<module>/statistics.py` contributes typed metrics through `apps.statistics.domain.Metric` / `Provider` when Statistics is installed. Statistics must never directly import feature ORM models. No provider should query the DB at import time.
- Every provider query MUST filter by the authorized `MetricContext` owner or `organization`; tests must confirm cross-user, cross-tenant and superuser isolation. Account and audit aggregate counts are system-superuser only. Never allow arbitrary user-selected ORM field expressions, SQL, or module imports.
- Mark each metric as a current `snapshot` or `period` aggregate. No silent approximation or historic stock inference from current balances. Company aggregates currently require active owner/admin membership; adding member-level aggregates requires an explicit product/privacy review.
