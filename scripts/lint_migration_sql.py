#!/usr/bin/env python3
"""Fail-closed static lint of source-owned PostgreSQL upgrade SQL.

Run after the catalog PostgreSQL Docker Compose integration job. A SQL linter
cannot validate data migrations or prove that a migration is operationally safe.
"""

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SQUAWK = ("uvx", "--from", "squawk-cli==2.65.0", "squawk")


def migration_candidates(root: Path) -> list[tuple[str, str]]:
    """Lint numbered upgrades; a new module's 0001 creates empty tables."""
    result: list[tuple[str, str]] = []
    for path in sorted((root / "apps").glob("*/migrations/[0-9]*.py")):
        version = path.stem.split("_", 1)[0]
        if version.isdecimal() and int(version) > 1:
            result.append((path.parents[1].name, path.stem))
    return result


def lint_upgrade_sql(root: Path = ROOT) -> None:
    upgrades = migration_candidates(root)
    if not upgrades:
        # Still verify that the pinned linter is installable, even before the
        # first versioned upgrade lands. Otherwise the CI stage is a no-op.
        subprocess.run([*SQUAWK, "--version"], cwd=root, check=True)
        print("No non-initial source-owned PostgreSQL migrations to lint.")
        return

    with TemporaryDirectory(prefix="primarykit-migration-sql-") as work:
        sql_paths: list[str] = []
        for app, revision in upgrades:
            rendered = subprocess.run(
                [
                    "docker",
                    "compose",
                    "exec",
                    "-T",
                    "api",
                    "python",
                    "manage.py",
                    "sqlmigrate",
                    app,
                    revision,
                ],
                cwd=root,
                check=True,
                text=True,
                capture_output=True,
            )
            if not rendered.stdout.strip():
                raise RuntimeError(
                    f"sqlmigrate generated no SQL for {app}.{revision}; refusing to skip review"
                )
            output = Path(work) / f"{app}-{revision}.sql"
            output.write_text(rendered.stdout, encoding="utf-8")
            sql_paths.append(str(output))
        # Squawk returns a nonzero code for violations and parsing errors.
        # Never suppress warnings or opt in to continue-on-error.
        subprocess.run([*SQUAWK, "--pg-version=17.0", *sql_paths], cwd=root, check=True)


if __name__ == "__main__":
    lint_upgrade_sql()
