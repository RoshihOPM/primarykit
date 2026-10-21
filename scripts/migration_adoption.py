#!/usr/bin/env python3
"""Read-only assessment of bundled migration histories in copied Django clients.

Never writes files, fakes migrations, modifies database state, or imports module
Python. A matching file graph does not mean migrations were safely applied.
"""

import argparse
import ast
import hashlib
import json
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


def adoption_plan(*, source: Path, project: Path) -> dict:
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
        if not client_folder.is_dir():
            status = "not_installed"
        else:
            client_history = _history(client_folder / "migrations")
            if source_history == client_history:
                status = "same_file_history"
            else:
                status = "manual_adoption_required"
        items.append(
            {
                "module": folder.name,
                "status": status,
                "source_revisions": sorted(source_history),
                "client_revisions": (
                    sorted(_history(client_folder / "migrations")) if client_folder.is_dir() else []
                ),
            }
        )
    return {
        "modules": items,
        "requires_manual_review": any(
            item["status"] == "manual_adoption_required" for item in items
        ),
        "limitations": (
            "File identities only. Validate applied django_migrations rows, "
            "real database schema, historical dependencies and data before adoption. "
            "Never overwrite or fake previously applied migrations."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--project", type=Path, required=True)
    options = parser.parse_args()
    print(
        json.dumps(
            adoption_plan(source=options.source, project=options.project),
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
