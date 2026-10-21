from pathlib import Path

from scripts.lint_migration_sql import migration_candidates


def test_upgrade_sql_linter_skips_only_initial_history(tmp_path: Path):
    migrations = tmp_path / "apps" / "jobs" / "migrations"
    migrations.mkdir(parents=True)
    for name in ("__init__.py", "0001_initial.py", "0002_add_status.py", "0003_schedule.py"):
        (migrations / name).write_text("")
    assert migration_candidates(tmp_path) == [
        ("jobs", "0002_add_status"),
        ("jobs", "0003_schedule"),
    ]
