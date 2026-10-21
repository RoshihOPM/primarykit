"""Opt-in three-way applying never silently changes contracts or client work."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.apply_module_upgrade import apply_three_way_updates
from scripts.new_project import create_project


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def commit(root: Path, message: str):
    git(root, "add", ".")
    git(root, "-c", "user.name=Tests", "-c", "user.email=tests@example.test", "commit", "-m", message)


def fixtures(tmp_path):
    source = create_project(tmp_path / "source", name="source-api", optional_apps={"audit"})
    client = create_project(tmp_path / "client", name="client-api", optional_apps={"audit"})
    original = "".join(f"# original {i}\n" for i in range(80))
    for target in (source, client):
        helper = target / "apps" / "audit" / "helper.py"
        helper.write_text(original)
    origin = client / "primarykit-origin.json"
    metadata = json.loads(origin.read_text())
    metadata["module_fingerprints"]["audit"]["helper.py"] = hashlib.sha256(
        original.encode()
    ).hexdigest()
    git(source, "init", "-q")
    commit(source, "baseline")
    metadata["module_source_refs"]["audit"] = git(source, "rev-parse", "HEAD")
    origin.write_text(json.dumps(metadata))
    git(client, "init", "-q")
    commit(client, "baseline")
    git(client, "checkout", "-b", "feat/upgrade")
    return source, client


def test_three_way_merges_disjoint_client_and_upstream_changes(tmp_path):
    source, client = fixtures(tmp_path)
    up = source / "apps" / "audit" / "helper.py"
    local = client / "apps" / "audit" / "helper.py"
    up.write_text(up.read_text().replace("# original 60", "# upstream 60"))
    commit(source, "upstream")
    local.write_text(local.read_text().replace("# original 2", "# client 2"))
    commit(client, "client customization")
    result = apply_three_way_updates(source=source, project=client)
    assert result["applied"] is True
    assert result["requires_client_pr"] is True
    assert "# client 2" in local.read_text()
    assert "# upstream 60" in local.read_text()
    metadata = json.loads((client / "primarykit-origin.json").read_text())
    assert metadata["module_fingerprints"]["audit"]["helper.py"] == hashlib.sha256(
        up.read_bytes()
    ).hexdigest()
    assert metadata["module_source_refs"]["audit"] == git(source, "rev-parse", "HEAD")
    assert git(client, "status", "--porcelain")
    assert apply_three_way_updates not in (None,)


def test_three_way_conflict_refuses_every_write(tmp_path):
    source, client = fixtures(tmp_path)
    up = source / "apps" / "audit" / "helper.py"
    local = client / "apps" / "audit" / "helper.py"
    up.write_text(up.read_text().replace("# original 5", "# upstream 5"))
    commit(source, "upstream")
    local.write_text(local.read_text().replace("# original 5", "# client 5"))
    commit(client, "client edit")
    original = local.read_bytes()
    origin = (client / "primarykit-origin.json").read_bytes()
    with pytest.raises(ValueError, match="merge"):
        apply_three_way_updates(source=source, project=client)
    assert local.read_bytes() == original
    assert (client / "primarykit-origin.json").read_bytes() == origin


def test_three_way_requires_clean_feature_branch_and_no_source_migrations(tmp_path):
    source, client = fixtures(tmp_path)
    up = source / "apps" / "audit" / "helper.py"
    up.write_text(up.read_text() + "# new upstream\n")
    commit(source, "upstream")
    git(client, "checkout", "-b", "main")
    with pytest.raises(ValueError, match="feature branch"):
        apply_three_way_updates(source=source, project=client)
    git(client, "checkout", "feat/upgrade")
    (client / "README.md").write_text("modified")
    with pytest.raises(ValueError, match="uncommitted"):
        apply_three_way_updates(source=source, project=client)
    git(client, "checkout", "--", "README.md")
    migrations = source / "apps" / "audit" / "migrations"
    migrations.mkdir()
    (migrations / "__init__.py").write_text("")
    (migrations / "0001_initial.py").write_text("# Schema requires review\n")
    commit(source, "schema migration")
    with pytest.raises(ValueError, match="schema adoption"):
        apply_three_way_updates(source=source, project=client)
