# PrimaryKit

**Language:** English · [Русский](README.ru.md)

**License:** [MIT](LICENSE) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Code of Conduct](CODE_OF_CONDUCT.md) · [Maintainer / branch-protection guide](docs/maintainer-playbook.md)

**PrimaryKit is a copy-based Django REST API project generator and portable module catalog.** Choose a set of modules, generate a standalone backend, then implement and deploy your own business rules. A generated application owns its code, migrations, dependencies, data, infrastructure and releases.

> **Status:** source version `0.1.0`, actively developed and publicly accessible. This repository is not a SaaS, a hosted backend, a microservices framework, or a shared runtime library. Modules are reusable starting points, not certified production-ready business solutions.
>
> **Public repository security status (2026-10-22):** `main` has an active, non-bypassable PR ruleset requiring `test` and `scan-history`; both checks passed on `df8282a`. The full manual history/IP rights review is **not signed off** ([#68](https://github.com/RoshihOPM/primarykit/issues/68)). See [project status](docs/en/project-status.md).

## Why PrimaryKit?

- **Independence:** generated backends have no runtime import or service dependency on the PrimaryKit source repository.
- **Composable Django/DRF modules:** a registry backed by `apps/<module>/manifest.py` resolves required dependencies and optional integrations.
- **Explicit data ownership:** generated clients create, review, version and migrate their **own** Django migrations. The source catalog does not ship reusable migration histories.
- **Safety by design:** deny-by-default authorization, owner/tenant scoping, scoped commands, PostgreSQL transaction boundaries and tests for supported paths.
- **Optional infrastructure:** PostgreSQL is the baseline; Redis, RabbitMQ, Celery, SeaweedFS/S3 and WebSockets are added only when needed.

## Quick start

Requires Python 3.13, [uv](https://docs.astral.sh/uv/), Git, PostgreSQL 17 and Docker Compose for the shown local database setup.

```bash
git clone https://github.com/RoshihOPM/primarykit.git
cd primarykit
uv sync --locked
uv run python scripts/new_project.py ../shop-api --name shop-api --apps catalog inventory orders sales payments statistics --git-init
cd ../shop-api
cp .env.example .env
docker compose up -d db
uv run python manage.py makemigrations users catalog inventory orders sales payments
uv run python manage.py migrate
python -m apps.core.doctor --strict
uv run python manage.py runserver
```

Test the API at `http://127.0.0.1:8000/health/live/`. Swagger is available at `/api/docs/` in debug/local settings. On PowerShell, replace `cp` with `Copy-Item`. **Commit the generated migrations to the client repository.**

This example uses standalone Catalog and Inventory. For tenant mode, include `organizations` with `catalog inventory` **before the first migration**; do not switch modes on an existing database without a reviewed data migration.

[Complete English guide](docs/en/getting-started.md) · [Русское руководство](docs/getting-started.md)

## Available modules

The source catalog currently contains **38** apps (three baseline and 35 selectable source modules):

| Area | Modules |
| --- | --- |
| Foundation | `core`, `users`, `notifications` |
| Identity and permissions | `organizations`, `rbac`, `audit`, `api_keys` |
| API and operations | `feature_flags`, `search`, `csv_exchange`, `idempotency`, `http_integrations`, `observability`, `usage_quotas` |
| Async and integrations | `tasks` (including recurring scheduler), `outbox`, `webhooks`, `cache`, `rate_limit`, `celery_tasks` |
| State and privacy | `workflows`, `privacy` |
| Messaging | `chat`, `realtime` (opt-in WebSocket transport) |
| Business examples | `storage`, `catalog`, `inventory`, `statistics`, `orders`, `sales`, `payments` |
| Classified ads | `listings` (moderation and opt-in photos), `favorites` (bookmarks and saved searches) |
| CRM building blocks | `kanban`, `leads`, `contacts`, `deals` (independent), `crm_pipeline` (opt-in transactional adapter) |

`users` includes per-user device/session management. `organizations` supplies a shared tenant permission policy adapter. There is also a **source-only module scaffold CLI** (not a runtime module) and dependency graph exporter.

For exact requirements, routes and compatibility constraints: [English module catalog](docs/en/modules.md) · [Русский каталог](docs/modules.md).

## CLI workflows

Generate a minimal backend:

```bash
uv run python scripts/new_project.py ../crm-api --name crm-api --git-init
```

Generate a project with a selected module composition:

```bash
uv run python scripts/new_project.py ../warehouse --name warehouse --apps inventory statistics
```

Install a trusted source module into a **previously generated PrimaryKit backend**:

```bash
python manage.py install_kit_module orders --source ../primarykit --dry-run
python manage.py install_kit_module orders --source ../primarykit
python manage.py makemigrations orders
python manage.py migrate
```

Installed modules register their Django applications and URLs via their manifests. A plain copy into an arbitrary non-PrimaryKit Django project is **not** guaranteed to work. There is **no automatic source update or migration** of client projects.

The source catalog additionally supports project presets, a project dry-run, a read-only module upgrade report and opt-in `--apply-safe` copying of unchanged non-contract Python files (see [updates](docs/en/module-updates.md)), an offline OpenAPI compatibility comparison and `scripts/module_scaffold.py` for creating a new source module.

## Security and production boundaries

- Owner/tenant permissions are enforced by each relevant service and API query. Merely installing RBAC or Organizations does not turn every other module into a tenant-aware feature.
- Orders and Sales store prices as integer minor monetary units. **Order prices are snapshots, not a trusted pricing engine.**
- **Payments does not process real payments.** A PaymentIntent is not settlement; only a privileged manual reconciliation is supplied. Implement and verify a real provider adapter before collecting funds.
- **Sales does not automatically decrement Inventory** or perform fiscalization. Orders, Sales and Payments are owner-scoped examples, not complete B2B commerce.
- Chat is private and scoped; WebSocket uses explicit authentication and PostgreSQL polling, which has documented scaling limits. No global subscriptions are enabled.
- Privacy retention never deletes client data by itself. Policies, handlers, legal holds, external effects and compliance obligations are owned by the generated client.
- PostgreSQL Tasks and Outbox provide at-least-once delivery, not exactly-once side effects. Redis does not become the authority for paid quotas or financial records.
- Production TLS, rate limiting at the edge where needed, secrets management, database backups/test restores, provider sandbox tests and security reviews are deployment responsibilities.

## Documentation

**[English documentation](docs/en/README.md)** · **[Русская документация](docs/README.md)**

- [Architecture and ownership](docs/en/architecture.md)
- [Module list, dependencies and routes](docs/en/modules.md)
- [Getting started](docs/en/getting-started.md)
- [Implemented features and limitations](docs/en/features.md) · [New module deep dives (#45–#52)](docs/en/README.md#newly-implemented-module-guides-45-52)
- [Production and security checklist](docs/en/operations.md)
- [Current project status](docs/en/project-status.md)

Detailed implementation-specific reference documents are presently maintained in `docs/` (Russian and English mixed). The English guides above cover the current module set and link to these source references.

## Contributing and quality gates

```bash
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check --settings=config.settings.test
uv run pytest
```

CI additionally exercises detached generated clients, PostgreSQL, Docker and optional services. It enforces an initial 40% aggregate coverage floor for Orders/Sales/Payments and audits locked production dependencies; optional infrastructure dependencies need separate review. See [agent development rules](AGENTS.md), [project roadmap](docs/module-roadmap.md) and [contributing](CONTRIBUTING.md).

**Stack:** Python 3.13 · Django 6.1 · DRF · PostgreSQL 17 · uv · Docker Compose · pytest · Ruff.

## AI-agent workflow

Generate a project, then inside the **generated client** run `python -m apps.core.agent_context --format markdown` to get an offline, project-specific agent brief. Give it to Codex together with `AGENTS.md`, relevant app files and tests. See [AI-assisted development](docs/ai-assisted-development.md).

## CRM starter (optional)

Select `--preset crm` to compose four standalone private API modules: Kanban, Leads, Contacts and Deals, plus opt-in `crm_pipeline` mapping for atomic Deal-to-Kanban projection. They have **no direct module dependencies or shared business model foreign keys**. Each can be installed individually with `--apps`. See [English CRM guide](docs/en/crm-starter.md) and [Russian CRM guide](docs/crm-starter.md).

## Classified listings (optional)

Select `--apps listings` or `--preset marketplace` for seller-owned moderated ads with public listing search, independent of Catalog and Inventory. Add `--apps favorites` for private bookmarks and saved searches (which also copies Listings). VIN/make/model integrations and promotion credits remain client-owned; optional listing photos are provided through a disabled-by-default private media adapter with explicit moderation. See [Listings](docs/listings.md) and [Favorites](docs/en/favorites.md).
