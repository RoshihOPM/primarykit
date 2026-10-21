import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import lint_migration_sql as lint


def add_migrations(root: Path, *revisions: str) -> None:
    migrations = root / "apps" / "jobs" / "migrations"
    migrations.mkdir(parents=True)
    for name in revisions:
        (migrations / name).write_text("", encoding="utf-8")


def test_upgrade_sql_linter_skips_only_initial_history(tmp_path: Path):
    add_migrations(
        tmp_path, "__init__.py", "0001_initial.py", "0002_add_status.py", "0003_schedule.py"
    )
    assert lint.migration_candidates(tmp_path) == [
        ("jobs", "0002_add_status"),
        ("jobs", "0003_schedule"),
    ]


def test_linter_runs_version_check_without_upgrade_migrations(tmp_path: Path, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(lint.subprocess, "run", run)
    lint.lint_upgrade_sql(tmp_path)
    assert calls == [([*lint.SQUAWK, "--version"], {"cwd": tmp_path, "check": True})]


def test_rendered_upgrade_sql_is_linted_by_pinned_squawk(tmp_path: Path, monkeypatch):
    add_migrations(tmp_path, "0001_initial.py", "0002_add_status.py", "0003_schedule.py")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        assert kwargs["check"] is True and kwargs["cwd"] == tmp_path
        if command[0] == "docker":
            assert kwargs["capture_output"] and kwargs["text"]
            return SimpleNamespace(stdout="ALTER TABLE example ADD COLUMN flag boolean;\n")
        assert command[: len(lint.SQUAWK)] == list(lint.SQUAWK)
        assert command[len(lint.SQUAWK)] == "--pg-version=17.0"
        sql_paths = command[len(lint.SQUAWK) + 1 :]
        assert len(sql_paths) == 2
        assert [Path(path).name for path in sql_paths] == [
            "jobs-0002_add_status.sql", "jobs-0003_schedule.sql"
        ]
        assert all(
            Path(path).read_text() == "ALTER TABLE example ADD COLUMN flag boolean;\n"
            for path in sql_paths
        )
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(lint.subprocess, "run", run)
    lint.lint_upgrade_sql(tmp_path)
    assert len(commands) == 3


@pytest.mark.parametrize("failure_stage", ["sqlmigrate", "squawk"])
def test_lint_failures_block_ci(tmp_path: Path, monkeypatch, failure_stage):
    add_migrations(tmp_path, "0002_add_status.py")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if command[0] == "docker":
            if failure_stage == "sqlmigrate":
                raise subprocess.CalledProcessError(1, command)
            return SimpleNamespace(stdout="ALTER TABLE t ADD COLUMN val int NOT NULL;\n")
        if failure_stage == "squawk":
            raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(lint.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        lint.lint_upgrade_sql(tmp_path)
    assert len(commands) == (1 if failure_stage == "sqlmigrate" else 2)


def test_empty_sqlmigrate_output_is_a_blocker(tmp_path: Path, monkeypatch):
    add_migrations(tmp_path, "0002_add_status.py")

    def run(command, **kwargs):
        assert command[0] == "docker", "Squawk should never see empty SQL"
        return SimpleNamespace(stdout="  \n")

    monkeypatch.setattr(lint.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="no SQL"):
        lint.lint_upgrade_sql(tmp_path)
