"""Adoption never mutates a client's applied migration graph."""

import pytest

from scripts.migration_adoption import adoption_plan
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
    assert any(item["module"] == "tasks" and item["status"] == "not_installed" for item in report["modules"])
