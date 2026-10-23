#!/usr/bin/env python3
"""Read-only assessment of bundled migration histories in copied Django clients.

Never writes files, fakes migrations, modifies database state, or imports module
Python. A matching file graph does not mean migrations were safely applied.
"""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path


def _schema_modes(root: Path) -> dict:
    origin = root / "primarykit-origin.json"
    if not origin.is_file():
        raise ValueError("Missing client provenance: manual schema adoption required")
    data = json.loads(origin.read_text(encoding="utf-8"))
    modes = data.get("schema_modes", {})
    if not isinstance(modes, dict):
        raise ValueError("Invalid pinned schema modes")
    settings_file = root / "config" / "settings" / "base.py"
    settings_tree = ast.parse(settings_file.read_text(encoding="utf-8"))
    for name, expected in modes.items():
        if name not in {"catalog", "inventory"} or expected not in {"tenant", "standalone"}:
            raise ValueError("Unexpected schema mode in provenance")
        key = name.upper() + "_MODE"
        expressions = [
            stmt.value
            for stmt in settings_tree.body
            if isinstance(stmt, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == key for t in stmt.targets)
        ]
        if len(expressions) != 1 or ast.literal_eval(expressions[0]) != expected:
            raise ValueError(f"Schema profile changed for {name}; manual migration review")
    return modes


def _history(folder: Path) -> dict[str, str]:
    if not folder.is_dir():
        return {}
    result = {}
    for file in sorted(folder.iterdir()):
        if file.name in {"__init__.py", "__pycache__"}:
            continue
        if file.suffix != ".py" or not file.stem[:1].isdigit() or file.is_symlink():
            raise ValueError(f"Unreviewed artifact in migration folder: {file.name}")
        if not file.is_file():
            raise ValueError("Invalid source migration history")
        result[file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
    return result


def _policy(source: Path) -> str:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    assignments = [
        item.value
        for item in tree.body
        if isinstance(item, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "MODULE" for t in item.targets)
    ]
    if len(assignments) != 1 or not isinstance(assignments[0], ast.Call):
        raise ValueError("Invalid source module manifest")
    entries = {item.arg: item.value for item in assignments[0].keywords}
    value = entries.get("migration_policy")
    return ast.literal_eval(value) if value is not None else "none"


def _read_postgres_migrations() -> set[tuple[str, str]]:
    """Read only Django's migration ledger from an explicitly selected PostgreSQL DB.

    The URL is supplied by DATABASE_URL, never printed, and session-level
    default_transaction_read_only prevents any accidental write in this session.
    No Django setup, migration runner or client imports are used.
    """
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise ValueError("Set an explicit PostgreSQL DATABASE_URL for --verify-postgres")

    import psycopg

    try:
        with psycopg.connect(
            database_url,
            connect_timeout=5,
            options="-c default_transaction_read_only=on -c statement_timeout=5000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SHOW transaction_read_only")
                if cursor.fetchone()[0] != "on":
                    raise ValueError("Refusing migration inspection without a read-only transaction")
                cursor.execute("SELECT app, name FROM django_migrations")
                return {(str(app), str(name)) for app, name in cursor.fetchall()}
    except psycopg.Error:
        # Driver exceptions may embed credentials/host details; never print them.
        raise ValueError(
            "Cannot read django_migrations from the selected PostgreSQL database"
        ) from None


def _applied_status(
    *, module: str, client_history: dict[str, str] | None, applied: set[tuple[str, str]]
) -> dict:
    """Compare DB ledger entries to client files; do not infer physical schema safety."""
    recorded = {name for app, name in applied if app == module}
    expected = {Path(filename).stem for filename in client_history or {}}
    if client_history is None:
        state = "not_installed" if not recorded else "orphaned_database_revisions"
    elif not recorded:
        state = "not_applied"
    elif recorded - expected:
        state = "unexpected_database_revisions"
    elif expected - recorded:
        state = "partially_applied"
    else:
        state = "all_recorded"
    return {
        "applied_status": state,
        "applied_revisions": sorted(recorded),
        "missing_revisions": sorted(expected - recorded),
        "unexpected_revisions": sorted(recorded - expected),
        "database_review_required": state not in {"not_installed", "all_recorded"},
    }


def adoption_plan(
    *,
    source: Path,
    project: Path,
    applied_migrations: set[tuple[str, str]] | None = None,
) -> dict:
    source, project = source.resolve(), project.resolve()
    if source == project:
        raise ValueError("Source and client must differ")
    _schema_modes(project)
    source_apps, client_apps = source / "apps", project / "apps"
    if not source_apps.is_dir() or not client_apps.is_dir():
        raise ValueError("Expected source and client apps directories")
    items = []
    for folder in sorted(source_apps.iterdir()):
        manifest = folder / "manifest.py"
        if not manifest.is_file() or _policy(manifest) != "bundled":
            continue
        source_history = _history(folder / "migrations")
        if not source_history:
            raise ValueError(f"Bundled module {folder.name} has no migration history")
        client_folder = client_apps / folder.name
        client_history = _history(client_folder / "migrations") if client_folder.is_dir() else None
        if client_history is None:
            status = "not_installed"
        elif source_history == client_history:
            status = "same_file_history"
        else:
            status = "manual_adoption_required"
        item = {
            "module": folder.name,
            "status": status,
            "source_revisions": sorted(source_history),
            "client_revisions": sorted(client_history or {}),
        }
        if applied_migrations is not None:
            item.update(
                _applied_status(
                    module=folder.name,
                    client_history=client_history,
                    applied=applied_migrations,
                )
            )
        items.append(item)
    return {
        "modules": items,
        "requires_manual_review": any(
            item["status"] == "manual_adoption_required"
            or item.get("database_review_required", False)
            for item in items
        ),
        "postgresql_checked": applied_migrations is not None,
        "limitations": (
            "File identities only. Validate applied django_migrations rows, "
            "real database schema, historical dependencies and data before adoption. "
            "A matching django_migrations ledger does NOT establish a safe physical schema, "
            "migration dependency graph, data integrity or correct database identity. "
            "Review those separately. Never overwrite or fake previously applied migrations."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument(
        "--verify-postgres",
        action="store_true",
        help="Opt-in read-only check of django_migrations using DATABASE_URL",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero if any installed module needs manual review",
    )
    options = parser.parse_args()
    applied = _read_postgres_migrations() if options.verify_postgres else None
    report = adoption_plan(
        source=options.source,
        project=options.project,
        applied_migrations=applied,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if options.strict and report["requires_manual_review"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
