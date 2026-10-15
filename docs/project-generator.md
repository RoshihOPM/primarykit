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

Always copied: `core`, `users`, `notifications`. Optional: `rbac`, `audit`, `storage`.

`users` currently depends on `notifications` because account verification uses its email transport. Audit is optional (core facade is a no-op when not installed). Storage and RBAC depend on Users.

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
