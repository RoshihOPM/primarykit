"""Adoption never mutates a client's applied migration graph."""

import pytest

from scripts.migration_adoption import _applied_status, _read_postgres_migrations, adoption_plan
from scripts.new_project import SOURCE_ROOT, create_project


def test_same_bundled_tasks_history_is_reported_without_changes(tmp_path):
    client = create_project(tmp_path / "client", name="example-client", optional_apps={"tasks"})
    migration = client / "apps" / "tasks" / "migrations" / "0001_initial.py"
    before = migration.read_bytes()
    report = adoption_plan(source=SOURCE_ROOT, project=client)
    tasks = next(item for item in report["modules"] if item["module"] == "tasks")
    assert tasks["status"] == "same_file_history"
    assert report["requires_manual_review"] is False
    assert migration.read_bytes() == before


def test_client_owned_different_history_must_not_be_overwritten(tmp_path):
    client = create_project(tmp_path / "client", name="example-client", optional_apps={"tasks"})
    migration = client / "apps" / "tasks" / "migrations" / "0001_initial.py"
    original = migration.read_text()
    migration.write_text(original + "\n# client extension\n")
    report = adoption_plan(source=SOURCE_ROOT, project=client)
    tasks = next(item for item in report["modules"] if item["module"] == "tasks")
    assert tasks["status"] == "manual_adoption_required"
    assert report["requires_manual_review"] is True
    assert migration.read_text() == original + "\n# client extension\n"


def test_adoption_refuses_changed_pinned_profile(tmp_path):
    client = create_project(
        tmp_path / "client",
        name="example-client",
        optional_apps={"catalog", "inventory", "organizations"},
    )
    config = client / "config" / "settings" / "base.py"
    config.write_text(
        config.read_text().replace('INVENTORY_MODE = "tenant"', 'INVENTORY_MODE = "standalone"')
    )
    with pytest.raises(ValueError, match="Schema profile changed"):
        adoption_plan(source=SOURCE_ROOT, project=client)


def test_adoption_on_minimal_client_is_read_only(tmp_path):
    client = create_project(tmp_path / "client", name="example-client")
    report = adoption_plan(source=SOURCE_ROOT, project=client)
    assert report["requires_manual_review"] is False
    assert any(
        item["module"] == "tasks" and item["status"] == "not_installed"
        for item in report["modules"]
    )


def test_applied_migrations_report_marks_clean_postgres_ledger(tmp_path):
    client = create_project(tmp_path / "client", name="example-client", optional_apps={"tasks"})
    report = adoption_plan(
        source=SOURCE_ROOT,
        project=client,
        applied_migrations={("tasks", "0001_initial"), ("auth", "0001_initial")},
    )
    assert report["postgresql_checked"] is True
    assert report["requires_manual_review"] is False
    assert report["modules"][0]["applied_status"] == "all_recorded"
    assert report["modules"][0]["missing_revisions"] == []


def test_applied_migrations_report_blocks_missing_or_foreign_records(tmp_path):
    client = create_project(tmp_path / "client", name="example-client", optional_apps={"tasks"})
    for applied, expected in [
        (set(), "not_applied"),
        ({("tasks", "0000_legacy")}, "unexpected_database_revisions"),
        (
            {("tasks", "0001_initial"), ("tasks", "0002_unknown")},
            "unexpected_database_revisions",
        ),
    ]:
        report = adoption_plan(source=SOURCE_ROOT, project=client, applied_migrations=applied)
        assert report["requires_manual_review"] is True
        assert report["modules"][0]["applied_status"] == expected


def test_applied_migrations_report_detects_orphaned_db_history(tmp_path):
    client = create_project(tmp_path / "client", name="example-client")
    report = adoption_plan(
        source=SOURCE_ROOT,
        project=client,
        applied_migrations={("tasks", "0001_initial")},
    )
    assert report["requires_manual_review"] is True
    assert report["modules"][0]["applied_status"] == "orphaned_database_revisions"


def test_applied_migrations_partial_status_is_fail_closed():
    result = _applied_status(
        module="tasks",
        client_history={"0001_initial.py": "hash1", "0002_more.py": "hash2"},
        applied={("tasks", "0001_initial")},
    )
    assert result["applied_status"] == "partially_applied"
    assert result["missing_revisions"] == ["0002_more"]
    assert result["database_review_required"] is True


def test_postgres_inventory_requires_explicit_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="explicit PostgreSQL"):
        _read_postgres_migrations()
    monkeypatch.setenv("DATABASE_URL", "sqlite:///local.db")
    with pytest.raises(ValueError, match="explicit PostgreSQL"):
        _read_postgres_migrations()


def test_postgres_inventory_is_read_only_and_never_logs_credentials(monkeypatch):
    import psycopg

    queries = []
    connection_kwargs = {}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query):
            queries.append(query)

        def fetchone(self):
            return ("on",)

        def fetchall(self):
            return [("tasks", "0001_initial"), ("auth", "0001_initial")]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return Cursor()

    def connect(*args, **kwargs):
        connection_kwargs.update(kwargs)
        return Connection()

    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://audit-user:PRIVATE_TEST_PASSWORD@127.0.0.1/client"
    )
    assert ("tasks", "0001_initial") in _read_postgres_migrations()
    assert "default_transaction_read_only=on" in connection_kwargs["options"]
    assert queries == [
        "SHOW transaction_read_only",
        "SELECT app, name FROM django_migrations",
    ]


def test_postgres_inventory_fails_if_transaction_is_writable(monkeypatch):
    import psycopg

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return self

        def execute(self, query):
            assert query == "SHOW transaction_read_only"

        def fetchone(self):
            return ("off",)

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@localhost/client")
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: Connection())
    with pytest.raises(ValueError, match="read-only"):
        _read_postgres_migrations()
