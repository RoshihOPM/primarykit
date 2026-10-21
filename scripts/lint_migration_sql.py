#!/usr/bin/env python3
"""Lint PostgreSQL upgrade SQL with pinned Squawk, after Docker Compose starts."""

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def migration_candidates(root: Path) -> list[tuple[str, str]]:
    """Exclude initial migrations: new empty tables have different DDL risks."""
    result: list[tuple[str, str]] = []
    for path in sorted((root / "apps").glob("*/migrations/[0-9]*.py")):
        version = path.stem.split("_", 1)[0]
        if not version.isdecimal() or int(version) <= 1:
            continue
        result.append((path.parents[1].name, path.stem))
    return result


def lint_upgrade_sql() -> None:
    upgrades = migration_candidates(ROOT)
    if not upgrades:
        print("No non-initial PostgreSQL migrations to lint.")
        return
    with TemporaryDirectory(prefix="primarykit-migration-sql-") as work:
        sql_paths: list[str] = []
        for app, revision in upgrades:
            rendered = subprocess.run(
                [
                    "docker", "compose", "exec", "-T", "api",
                    "python", "manage.py", "sqlmigrate", app, revision,
                ],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            )
            output = Path(work) / f"{app}-{revision}.sql"
            output.write_text(rendered.stdout, encoding="utf-8")
            sql_paths.append(str(output))
        subprocess.run(
            ["uvx", "--from", "squawk-cli==2.65.0", "squawk", *sql_paths],
            cwd=ROOT,
            check=True,
        )


if __name__ == "__main__":
    lint_upgrade_sql()
