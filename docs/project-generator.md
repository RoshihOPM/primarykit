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

`users` currently depends on `notifications` because account verification uses its email transport. Audit is optional (core facade is a no-op when not installed). Storage depends only on Users and works without Organizations; RBAC depends on Users. Catalog and Inventory depend on Organizations. These dependencies are automatically selected.

## What generator does

- Copies the source template excluding `.git`, `.env`, caches, local media, venv, generated migrations and the generator itself.
- Prunes omitted optional App directories, their `INSTALLED_APPS` entries and URL routes.
- Adapts GitHub Actions migration setup, generated README and project name in both `pyproject.toml` and `uv.lock`.
- Writes `primarykit-origin.json` with copied modules and source version.
- `--git-init` initializes local Git history on main; no GitHub remote is created and no push is performed.

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

`--apps inventory` automatically includes `catalog` and `organizations`.
`--apps storage` alone creates owner-private `/api/v1/files/` endpoints, without Organizations. If you also select Organizations, the generator adds `/api/v1/organizations/{org_id}/files/`. The two scopes use the same Storage service with separate authorization policies.
Even `--apps catalog` includes `organizations`. API routes are scoped as
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

**Honest dependency boundary:** `storage` works with the baseline without Organizations. `inventory` still requires both `catalog` and `organizations` in its existing ORM. The installer selects that dependency closure automatically; copying only `inventory/` without the required folders fails fast rather than permitting unsafe behavior. Standalone Inventory is a separate future schema/API design, not accomplished by manifest discovery.

For copied modules that already have historical migrations, preserve them. For source-catalog modules without migrations, generate migrations **once in the new project** and commit them. Never regenerate the initial migrations of a running client.
