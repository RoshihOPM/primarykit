# Getting started with PrimaryKit

**Language:** English · [Русский](../getting-started.md) · [Documentation index](README.md)

PrimaryKit **copies source code** into a new self-contained Django/DRF backend. It does not provision cloud infrastructure or provide a hosted API. Work from a trusted PrimaryKit checkout.

## Prerequisites

- Python **3.13**, Git, [uv](https://docs.astral.sh/uv/).
- PostgreSQL **17**; Docker Compose is convenient for the local example.
- A separate target directory that does not exist yet.

## 1. Generate and launch a minimal backend

```bash
git clone https://github.com/RoshihOPM/primarykit.git
cd primarykit
uv sync --locked --all-groups
uv run python scripts/new_project.py ../my-api --name my-api --git-init

cd ../my-api
cp .env.example .env
docker compose up -d db
uv sync --locked --all-groups
uv run python -m apps.core.doctor --strict
uv run python manage.py makemigrations users --noinput
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Open `/health/live/` and `/api/docs/` (Swagger in local/debug mode). On Windows PowerShell use `Copy-Item .env.example .env`. Set a unique local `DJANGO_SECRET_KEY` and inspect `DATABASE_URL`; never commit real secrets.

**Commit the generated `apps/*/migrations/` files to the new client's Git repository.** The original source catalog intentionally has no migration history to reuse. Do not delete or regenerate existing production migrations during an upgrade.

## 2. Generate a backend with business modules

```bash
cd ../primarykit
uv run python scripts/new_project.py ../shop-api --name shop-api \
  --apps catalog inventory orders sales payments statistics audit --git-init
cd ../shop-api
cp .env.example .env
docker compose up -d db
uv run python manage.py makemigrations users catalog inventory orders sales payments audit
uv run python manage.py migrate
uv run python -m apps.core.doctor --strict
uv run pytest
```

The example is **owner-scoped**: Catalog and Inventory are standalone, Orders/Sales/Payments are not multi-tenant commerce, and a Sale does not automatically deduct stock. Choose `--apps organizations catalog inventory` to enable tenant-specific Catalog and Inventory **before** generating the first migrations. A populated schema cannot safely switch modes by toggling a setting.

The generator resolves mandatory dependencies. It will not silently install optional infrastructure dependencies, apply migrations or modify a running application.

## 3. Source-only generator and module authoring tools

```bash
# Source repository only:
uv run python scripts/new_project.py --list-presets
uv run python scripts/new_project.py ../preview --name preview-api --preset marketplace --dry-run
python scripts/module_scaffold.py create reviews --requires users --dry-run
python scripts/module_scaffold.py graph --format dot > module-graph.dot
```

Presets choose a set of copied features; inspect the CLI output and selected modules before using them as a client architecture. Dry-run must not create the target directory. The scaffold creates `apps/<name>/manifest.py`, an AppConfig and starter tests **in the source catalog**; it is absent from generated client repos and contains no business code.

Read [generator details](../project-generator.md), [scaffold](../module-scaffold.md) and [dependency graph](modules.md).

## 4. Add a trusted module to an existing generated project

```bash
cd ../my-api
python manage.py install_kit_module orders --source ../primarykit --dry-run
python manage.py install_kit_module orders --source ../primarykit
python manage.py makemigrations orders
python manage.py migrate
```

This command copies the required module closure from **trusted** source and does not overwrite an existing module. For generated clients with provenance metadata, it atomically records initial SHA-256 file snapshots for each newly installed module. Recheck the schema, routes, access policies and tests before deploying. **Add any new migration-owning app to the client's CI `makemigrations` steps and commit the generated migrations.** Installing into arbitrary third-party Django projects is not a supported promise.

For upstream changes use the **read-only** module upgrade checker and review modifications and migration diffs in each generated client. No automatic update or production migration is provided.

## 5. Validate the generated backend

```bash
uv run python -m apps.core.doctor --strict
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check --settings=config.settings.test
uv run pytest
```

The doctor is a static offline check; it does not test database transactions or deployment security. For modules involving payments, tenant access, concurrency, realtime, legal retention or a scheduler, run their PostgreSQL integration tests and perform a deployment-specific review.

See [production checklist](operations.md), [architecture](architecture.md), and [module catalog](modules.md).
