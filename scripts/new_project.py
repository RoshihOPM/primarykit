#!/usr/bin/env python3
"""Copy a standalone PrimaryKit Django backend with selected optional apps."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
# Direct execution (python scripts/new_project.py) has scripts/ as sys.path[0].
if __package__ in (None, ""):
    sys.path.insert(0, str(SOURCE_ROOT))

from apps.core.doctor import inspect_project  # noqa: E402
from apps.core.module_registry import dependency_closure, discover_modules  # noqa: E402
from scripts.presets import PRESETS  # noqa: E402

REQUIRED_APPS = frozenset({"core", "users", "notifications"})
AVAILABLE_MODULES = discover_modules()
OPTIONAL_APPS = frozenset(AVAILABLE_MODULES) - REQUIRED_APPS
MIGRATION_APPS = (
    "users",
    "audit",
    "storage",
    "catalog",
    "inventory",
    "organizations",
    "orders",
    "sales",
    "payments",
    "tasks",
    "webhooks",
    "api_keys",
)
# Statistics uses existing module data only; it has no persistence migrations.


def _ignore_excluded(directory, names):
    ignored = set()
    for name in names:
        # Source catalog migrations are transient per-mode CI files. Each copied
        # client must generate its own schema after CATALOG_MODE/INVENTORY_MODE is pinned.
        if Path(directory).parent.name == "apps" and name == "migrations":
            ignored.add(name)
        if name in {
            ".git",
            ".venv",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            "media",
            "staticfiles",
            ".idea",
            ".vscode",
        }:
            ignored.add(name)
        if name.startswith(".env") and name != ".env.example":
            ignored.add(name)
        if name.endswith(".sqlite3") or name.endswith(".pyc"):
            ignored.add(name)
    return ignored


def _replace_one(path: Path, old: str, new: str):
    source = path.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise RuntimeError(f"Template drift in {path}: expected one match for {old!r}")
    path.write_text(source.replace(old, new), encoding="utf-8")


def project_plan(*, requested_apps: set[str], preset: str | None = None) -> dict:
    """Resolve a preset without changing either the kit or the destination."""
    if preset is not None and preset not in PRESETS:
        raise ValueError(f"Unknown preset: {preset}")
    apps = set(requested_apps) | set(PRESETS[preset]["apps"] if preset else ())
    if not apps <= OPTIONAL_APPS:
        raise ValueError("Unknown optional apps: " + ", ".join(sorted(apps - OPTIONAL_APPS)))
    selected = dependency_closure(AVAILABLE_MODULES, set(REQUIRED_APPS) | apps)
    return {
        "preset": preset,
        "requested_apps": sorted(apps),
        "included_apps": sorted(selected),
        "catalog_mode": "tenant" if {"catalog", "organizations"} <= selected else "standalone",
        "inventory_mode": (
            "tenant" if {"inventory", "catalog", "organizations"} <= selected else "standalone"
        ),
        "migrations": [app for app in MIGRATION_APPS if app in selected],
    }


def _module_fingerprints(root: Path, selected: set[str]) -> dict[str, dict[str, str]]:
    """Persist initial module file digests, not client secrets or file contents."""
    result = {}
    for name in sorted(selected):
        folder = root / "apps" / name
        result[name] = {
            file.relative_to(folder).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in sorted(folder.rglob("*.py"))
            if "migrations" not in file.parts and "__pycache__" not in file.parts
        }
    return result


def create_project(
    destination: Path,
    *,
    name: str,
    optional_apps: set[str] | frozenset[str] = frozenset(),
    git_init: bool = False,
    preset: str | None = None,
) -> Path:
    """Copy the template. No network, package install, migrations or deployment."""
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,62}", name):
        raise ValueError("Project name must be lowercase kebab-case, 2-63 characters")
    plan = project_plan(requested_apps=set(optional_apps), preset=preset)

    target = destination.expanduser().resolve()
    root = SOURCE_ROOT.resolve()
    if target == root or target.is_relative_to(root):
        raise ValueError("Create projects outside the PrimaryKit source repository")
    if target.exists():
        raise FileExistsError(f"Destination already exists: {target}")

    selected = set(plan["included_apps"])
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(root, target, ignore=_ignore_excluded)
        for module in OPTIONAL_APPS - selected:
            shutil.rmtree(target / "apps" / module)
        if "storage" not in selected:
            (target / "compose.seaweedfs.yaml").unlink()
        if not {"cache", "celery_tasks"} & selected:
            (target / "compose.redis.yaml").unlink()
        if "celery_tasks" not in selected:
            (target / "compose.celery.yaml").unlink()
            (target / "compose.celery.prod.yaml").unlink()

        # Generator remains with the source catalog only, not in client projects.
        shutil.rmtree(target / "scripts")
        (target / "apps" / "core" / "tests" / "test_project_generator.py").unlink()
        (target / "apps" / "core" / "tests" / "test_doctor.py").unlink()
        (target / "apps" / "core" / "tests" / "test_module_upgrade.py").unlink()
        # Installed apps and URLs are discovered from each copied manifest.py.

        migrations = " ".join(a for a in MIGRATION_APPS if a in selected)
        workflow = target / ".github" / "workflows" / "ci.yaml"
        raw = workflow.read_text(encoding="utf-8")
        phrase = "makemigrations users audit storage catalog inventory organizations orders sales payments tasks webhooks api_keys --noinput"
        if raw.count(phrase) != 2:
            raise RuntimeError("CI migration template has changed")
        raw = raw.replace(phrase, f"makemigrations {migrations} --noinput")
        start_marker = "      # PRIMARYKIT-GENERATOR-SMOKE-START\n"
        end_marker = "      # PRIMARYKIT-GENERATOR-SMOKE-END\n"
        if raw.count(start_marker) != 1 or raw.count(end_marker) != 1:
            raise RuntimeError("Missing generator CI smoke test markers")
        start = raw.index(start_marker)
        end = raw.index(end_marker, start) + len(end_marker)
        workflow.write_text(raw[:start] + raw[end:], encoding="utf-8")

        # Pin app schemas before the first migration; later module copies cannot
        # implicitly switch personal data into tenant-owned tables.
        catalog_mode = plan["catalog_mode"]
        inventory_mode = plan["inventory_mode"]
        if catalog_mode != "tenant":
            _replace_one(
                target / "config/settings/base.py",
                'CATALOG_MODE = "tenant"',
                'CATALOG_MODE = "standalone"',
            )
        if inventory_mode != "tenant":
            _replace_one(
                target / "config/settings/base.py",
                'INVENTORY_MODE = "tenant"',
                'INVENTORY_MODE = "standalone"',
            )
        if "cache" in selected:
            _replace_one(
                target / ".env.example",
                "REDIS_CACHE_KEY_PREFIX=primarykit-dev",
                f"REDIS_CACHE_KEY_PREFIX={name}-dev",
            )
        # Client-facing API branding belongs to the generated product, not the kit.
        _replace_one(
            target / "config/settings/base.py",
            '"TITLE": "PrimaryKit API"',
            f'"TITLE": "{name} API"',
        )
        _replace_one(
            target / "config/settings/base.py",
            '"DESCRIPTION": "Reusable Django API backend"',
            '"DESCRIPTION": "Independent Django API backend"',
        )
        # uv.lock's only virtual root package entry has to match pyproject.name.
        _replace_one(target / "pyproject.toml", 'name = "primarykit"', f'name = "{name}"')
        _replace_one(target / "uv.lock", 'name = "primarykit"', f'name = "{name}"')

        source_version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]["version"]
        metadata = {
            "origin": "RoshihOPM/primarykit",
            "source_version": source_version,
            "preset": preset,
            "included_apps": sorted(selected),
            "module_fingerprints": _module_fingerprints(target, selected),
            "migration_policy": "Generate once and commit all client migrations",
        }
        (target / "primarykit-origin.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (target / "README.md").write_text(
            f"# {name}\n\n"
            "Independent Django project created from copied starter source.\n\n"
            "This repository owns all business rules, Django apps, dependencies, migrations "
            "and deployments. The source constructor is not needed at runtime.\n"
            "Optional primarykit-origin.json is only provenance metadata and may be deleted.\n\n"
            f"## Selected apps\n\n{', '.join(sorted(selected))}\n\n"
            f"Preset: {preset or 'custom'}\n\n"
            "## Development startup\n\n"
            "```bash\n"
            "cp .env.example .env\n"
            "docker compose up --build -d\n"
            f"docker compose exec api python manage.py makemigrations {migrations}\n"
            "docker compose exec api python manage.py migrate\n"
            "```\n\n"
            "Commit the generated migrations to **this project's Git repository**.\n"
            "Run `python -m apps.core.doctor --strict` to validate copied modules "
            "without Django startup, database access, or the source kit.\n"
            "Configure SMTP, object storage, secrets and reverse proxy before production.\n"
            + (
                "SeaweedFS: docker compose -f compose.yaml -f compose.seaweedfs.yaml up -d --build\n"
                if "storage" in selected
                else ""
            )
            + (
                "\nNative CacheService: install `uv add 'redis>=8,<9'` (Cache only), "
                "set REDIS_CACHE_ENABLED=true and configure a unique Redis key prefix. "
                "Use compose.redis.yaml for development.\n"
                if "cache" in selected and "celery_tasks" not in selected
                else ""
            )
            + (
                "\nCache + Celery: install `uv add 'celery[redis]>=5.6,<6' "
                "'redis>=6.2,<6.5'` for the shared Redis result-backend stack. "
                "The native CacheService works with this compatible redis-py line.\n"
                if {"cache", "celery_tasks"} <= selected
                else ""
            )
            + (
                "\nCelery: install `uv add 'celery>=5.6,<6'` for RabbitMQ-only, "
                "or `uv add 'celery[redis]>=5.6,<6' 'redis>=6.2,<6.5'` "
                "if a Redis result backend is needed. Configure the broker and "
                "use compose.celery.yaml. PostgreSQL Tasks remains independent.\n"
                if "celery_tasks" in selected and "cache" not in selected
                else ""
            )
            + (
                "\nFeature flags: configure FEATURE_FLAGS in your own Django settings; "
                "missing flags are disabled and never grant permissions.\n"
                if "feature_flags" in selected
                else ""
            )
            + (
                "\nAPI keys: configure API_KEY_SCOPE_PERMISSIONS and your own authorized "
                "issuance/revocation endpoints. No credentials are exposed by default. "
                "Create and commit client-owned api_keys migrations.\n"
                if "api_keys" in selected
                else ""
            )
            + "See docs/architecture.md and AGENTS.md for conventions.\n",
            encoding="utf-8",
        )

        # Fail during generation when copied modules or dependencies violate
        # the offline portability contract. No DB or Django startup is needed.
        report = inspect_project(target)
        if report.failed(strict=True):
            details = "; ".join(f"{item.code}: {item.detail}" for item in report.findings)
            raise RuntimeError(f"Generated project did not pass doctor: {details}")

        if git_init:
            subprocess.run(
                ["git", "init", "-b", "main"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
            )
        return target
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Create independent Django backend from PrimaryKit"
    )
    parser.add_argument("destination", type=Path, nargs="?", help="New project directory")
    parser.add_argument("--name", help="New pyproject name, e.g. auto-market")
    parser.add_argument("--preset", choices=sorted(PRESETS), help="Optional starter profile")
    parser.add_argument("--list-presets", action="store_true", help="Show available profiles")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without any filesystem writes")
    parser.add_argument("--apps", nargs="*", choices=sorted(OPTIONAL_APPS), default=[])
    parser.add_argument("--git-init", action="store_true", help="Initialize new Git main branch")
    args = parser.parse_args()
    if args.list_presets:
        print(json.dumps(PRESETS, indent=2, ensure_ascii=False))
        return
    if not args.name or args.destination is None:
        parser.error("destination and --name are required unless --list-presets is set")
    if args.dry_run:
        print(json.dumps(project_plan(requested_apps=set(args.apps), preset=args.preset), indent=2))
        return
    target = create_project(
        args.destination,
        name=args.name,
        optional_apps=set(args.apps),
        git_init=args.git_init,
        preset=args.preset,
    )
    copied = set(project_plan(requested_apps=set(args.apps), preset=args.preset)["included_apps"])
    print(f"Created {target} with apps: {', '.join(sorted(copied))}")
    print(
        "Next: run python -m apps.core.doctor --strict, configure .env, "
        "uv sync --locked, create and commit client-owned migrations."
    )


if __name__ == "__main__":
    main()
