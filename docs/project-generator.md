# New Project Generator — v0.1

## Goal

Create a **completely independent Django repository** from PrimaryKit without pip-installed shared packages or source-catalog migration history. Module source is physically copied; later upgrades require a human review.

## Usage

```bash
uv run python scripts/new_project.py ../automarket --name automarket --apps rbac audit storage --git-init
cd ../automarket
cp .env.example .env
uv sync --locked
uv run python manage.py makemigrations users audit storage
uv run python manage.py migrate
uv run pytest
```

For minimal API:

```bash
uv run python scripts/new_project.py ../crm-api --name crm-api --git-init
```

Always copied: `core`, `users`, `notifications`. Optional: `rbac`, `audit`, `storage`, `organizations`, `catalog`, `inventory`.

`users` currently depends on `notifications` because account verification uses its email transport. Audit is optional (core facade is a no-op when not installed). Storage depends only on Users and works without Organizations; RBAC depends on Users. Catalog and Inventory work in standalone mode without other business modules. To start in tenant mode, select Organizations alongside Catalog (and Catalog plus Organizations alongside Inventory). The generator pins the schema mode before migrations.

## What generator does

- Copies the source template excluding `.git`, `.env`, caches, local media, venv, generated migrations and the generator itself.
- Prunes omitted optional App directories, their `INSTALLED_APPS` entries and URL routes.
- Adapts GitHub Actions migration setup, generated README and project name in both `pyproject.toml` and `uv.lock`.
- Writes `primarykit-origin.json` with copied modules and source version.
- `--git-init` initializes local Git history on main; no GitHub remote is created and no push is performed.

## Optional Redis Cache and Celery adapters

`--apps cache` and `--apps celery_tasks` are independent selections, do not create a dependency on the source kit or require `tasks`.
The generator includes `compose.redis.yaml` for Redis/Celery selections and `compose.celery.yaml` + `compose.celery.prod.yaml` only for Celery. Client projects opt into third-party packages explicitly (`uv add 'redis>=6,<7'`, `uv add 'celery[redis]>=5.6,<6'`) and commit their **own** lockfile. These adapters have no migrations. See [cache](redis-cache.md) and [Celery](celery-rabbitmq.md).

## Detached project verification

```bash
cd ../automarket
python -m apps.core.doctor --strict
```

The doctor is included in copied `apps/core/` and never imports/contacts PrimaryKit. The generator also runs these static checks before returning. This is a preflight, not a substitute for Django migrations, PostgreSQL tests or client business review. See [independent projects](independent-projects.md), [doctor](doctor.md) and [architecture recipes](architecture-recipes.md).

## Safety / limitations

- Refuses existing destinations and directories inside PrimaryKit.
- Does not execute migrations, install dependencies, provision infrastructure, deploy, or upload anything to GitHub.
- Projects own migrations and must commit them. Never remove existing migration history when updating modules.
- Omitted app documentation remains as an upstream reference; the generated README and installed app list define actual capabilities.
- Template drift intentionally fails rather than silently producing an invalid project.
- Source version records kit package version, **not** the precise Git commit. Record a commit pin manually for deterministic production provenance.
- `uv.lock` virtual root package name is replaced; CI verifies locked sync on generated project.

## Generate a tenant-scoped warehouse system

```bash
uv run python scripts/new_project.py ../warehouse-api --name warehouse-api --apps inventory audit storage --git-init
cd ../warehouse-api
cp .env.example .env
uv sync --locked --all-groups
uv run python manage.py makemigrations users audit storage organizations catalog inventory
uv run python manage.py migrate
uv run pytest
```

`--apps inventory` is standalone and has no Catalog/Organizations FKs. Tenant Inventory requires an explicit `--apps inventory catalog organizations` selection.
`--apps storage` alone creates owner-private `/api/v1/files/` endpoints, without Organizations. If you also select Organizations, the generator adds `/api/v1/organizations/{org_id}/files/`. The two scopes use the same Storage service with separate authorization policies.
Standalone `--apps catalog` has no Organizations dependency. Tenant API routes are scoped as
`/api/v1/organizations/{org_id}/catalog/` and `/inventory/`.
Creating a company via `POST /api/v1/organizations/` is the first step.

**Storage schema change:** Storage holds an optional opaque `organization_id` UUID rather than a foreign key to another bounded context. Unscoped personal rows use null. Organization-scoped rows must always pass active membership checks; never trust a user-supplied organization id. Existing clients require a reviewed migration from the old mandatory FK, and must preserve their committed migration history.

**Client upgrade warning:** copying a newer kit module into a pre-existing
database requires an explicit data-migration plan. Never assign all existing
products, warehouses or movements to an arbitrary company. Follow the
Catalog and Inventory architecture migration playbooks.

## Copy an additional module into an existing generated project

```bash
# Run inside the generated project; an independent copied module also works via file copy:
python manage.py install_kit_module storage --source ../primarykit
python manage.py makemigrations storage
python manage.py migrate

# Install an existing feature bundle with all its required submodules:
python manage.py install_kit_module inventory --source ../primarykit --dry-run
python manage.py install_kit_module inventory --source ../primarykit
python manage.py makemigrations organizations catalog inventory
python manage.py migrate
```

Modules are detected by the presence of `apps/<name>/manifest.py`. No `INSTALLED_APPS` or `config/urls.py` edits are necessary. Source checkout must be trusted; never copy unreviewed code into a production server. The installer is an explicit filesystem operation; it does **not** perform migrations, deploy, install external pip dependencies or overwrite an existing module. Restart running Django processes after copying.

**Schema boundary:** standalone Inventory and Catalog now have their own models and require no other business modules. The original tenant implementation still requires Catalog and Organizations when enabled; installing another app later does not silently flip the persisted model mode. See ADR 0005.

For copied modules that already have historical migrations, preserve them. For source-catalog modules without migrations, generate migrations **once in the new project** and commit them. Never regenerate the initial migrations of a running client.

## Fully independent Catalog / Inventory (schema modes)

```bash
uv run python scripts/new_project.py ../catalog-alone --name catalog-alone --apps catalog
uv run python scripts/new_project.py ../inventory-alone --name inventory-alone --apps inventory
uv run python scripts/new_project.py ../b2b-stock --name b2b-stock --apps organizations catalog inventory
```

Catalog-only and Inventory-only projects install **no extra business app**. The generator pins `CATALOG_MODE` and `INVENTORY_MODE` to `standalone` in standalone projects. For a selected company-integrated bundle it pins `tenant` before the project's first migration. Do not change a pinned schema mode on a populated database. The original tenant models, routes and branch authorization are preserved for B2B projects.

For an existing generated project that has no Catalog/Inventory, a raw copy or `install_kit_module` installs standalone apps when their modes in settings are `standalone`. Verify these settings before generating migrations. No runtime magic migrates existing rows or connects inventory SKUs to Catalog SKUs.

## Statistics: optional metrics provided by installed modules

```bash
uv run python scripts/new_project.py ../stats-alone --name stats-alone --apps statistics
uv run python scripts/new_project.py ../warehouse-stats --name warehouse-stats --apps statistics inventory
uv run python scripts/new_project.py ../company-stats --name company-stats --apps statistics organizations catalog inventory
```

Statistics adds **no database tables**, and no extra required Catalog/Inventory/Organizations modules. Its local `manifest.py` auto-registers the personal, conditional tenant, and system statistics routes. Installed modules with `statistics.py` provide their own safe metric definitions. Personal and tenant mode providers respect the project's pinned schema choice. See [Statistics architecture](statistics-architecture.md).
