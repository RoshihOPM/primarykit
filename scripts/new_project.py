#!/usr/bin/env python3
"""Copy a standalone PrimaryKit Django backend with selected optional apps."""

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_APPS = frozenset({"core", "users", "notifications"})
OPTIONAL_APPS = frozenset({"rbac", "audit", "storage", "catalog", "inventory", "organizations"})
MIGRATION_APPS = ("users", "audit", "storage", "catalog", "inventory", "organizations")

URL_ROWS = {
    "rbac": '    path("api/v1/admin/rbac/", include("apps.rbac.urls")),\n',
    "audit": '    path("api/v1/admin/audit/", include("apps.audit.urls")),\n',
    "storage": '    path("api/v1/", include("apps.storage.urls")),\n',
    "catalog": '    path("api/v1/catalog/", include("apps.catalog.urls")),\n',
    "inventory": '    path("api/v1/inventory/", include("apps.inventory.urls")),\n',
    "organizations": '    path("api/v1/", include("apps.organizations.urls")),\n',
}


def _ignore_excluded(directory, names):
    ignored = set()
    for name in names:
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


def create_project(
    destination: Path,
    *,
    name: str,
    optional_apps: set[str] | frozenset[str] = frozenset(),
    git_init: bool = False,
) -> Path:
    """Copy the template. No network, package install, migrations or deployment."""
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,62}", name):
        raise ValueError("Project name must be lowercase kebab-case, 2-63 characters")
    if not set(optional_apps).issubset(OPTIONAL_APPS):
        raise ValueError(
            "Unknown optional apps: " + ", ".join(sorted(set(optional_apps) - OPTIONAL_APPS))
        )

    target = destination.expanduser().resolve()
    root = SOURCE_ROOT.resolve()
    if target == root or target.is_relative_to(root):
        raise ValueError("Create projects outside the PrimaryKit source repository")
    if target.exists():
        raise FileExistsError(f"Destination already exists: {target}")

    selected = set(REQUIRED_APPS) | set(optional_apps)
    if "inventory" in selected:
        selected.add("catalog")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(root, target, ignore=_ignore_excluded)
        for module in OPTIONAL_APPS - selected:
            shutil.rmtree(target / "apps" / module)
        if "storage" not in selected:
            (target / "compose.seaweedfs.yaml").unlink()

        # Generator remains with the source catalog only, not in client projects.
        shutil.rmtree(target / "scripts")
        (target / "apps" / "core" / "tests" / "test_project_generator.py").unlink()
        settings = target / "config" / "settings" / "base.py"
        routes = target / "config" / "urls.py"
        for module in OPTIONAL_APPS - selected:
            _replace_one(settings, f'    "apps.{module}",\n', "")
            _replace_one(routes, URL_ROWS[module], "")

        migrations = " ".join(a for a in MIGRATION_APPS if a in selected)
        workflow = target / ".github" / "workflows" / "ci.yaml"
        raw = workflow.read_text(encoding="utf-8")
        phrase = "makemigrations users audit storage catalog inventory organizations --noinput"
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

        # uv.lock's only virtual root package entry has to match pyproject.name.
        _replace_one(target / "pyproject.toml", 'name = "primarykit"', f'name = "{name}"')
        _replace_one(target / "uv.lock", 'name = "primarykit"', f'name = "{name}"')

        metadata = {
            "origin": "RoshihOPM/primarykit",
            "source_version": "0.1.0",
            "included_apps": sorted(selected),
            "migration_policy": "Generate once and commit all client migrations",
        }
        (target / "primarykit-origin.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (target / "README.md").write_text(
            f"# {name}\n\n"
            "Independent Django project generated from PrimaryKit.\n\n"
            f"## Selected apps\n\n{', '.join(sorted(selected))}\n\n"
            "## Development startup\n\n"
            "```bash\n"
            "cp .env.example .env\n"
            "docker compose up --build -d\n"
            f"docker compose exec api python manage.py makemigrations {migrations}\n"
            "docker compose exec api python manage.py migrate\n"
            "```\n\n"
            "Commit the generated migrations to **this project's Git repository**.\n"
            "Configure SMTP, object storage, secrets and reverse proxy before production.\n"
            + (
                "SeaweedFS: docker compose -f compose.yaml -f compose.seaweedfs.yaml up -d --build\n"
                if "storage" in selected
                else ""
            )
            + "See docs/architecture.md and AGENTS.md for conventions.\n",
            encoding="utf-8",
        )

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
    parser.add_argument("destination", type=Path, help="New project directory (must not exist)")
    parser.add_argument("--name", required=True, help="New pyproject name, e.g. auto-market")
    parser.add_argument("--apps", nargs="*", choices=sorted(OPTIONAL_APPS), default=[])
    parser.add_argument("--git-init", action="store_true", help="Initialize new Git main branch")
    args = parser.parse_args()
    target = create_project(
        args.destination,
        name=args.name,
        optional_apps=set(args.apps),
        git_init=args.git_init,
    )
    copied = set(REQUIRED_APPS) | set(args.apps)
    if "inventory" in copied:
        copied.add("catalog")
    print(f"Created {target} with apps: {', '.join(sorted(copied))}")
    print("Next: copy .env.example to .env, run uv sync --locked, generate migrations and test.")


if __name__ == "__main__":
    main()
