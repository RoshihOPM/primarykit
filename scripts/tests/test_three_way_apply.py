"""Opt-in three-way applying never silently changes contracts or client work."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts import apply_module_upgrade
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
    git(
        root,
        "-c",
        "user.name=Tests",
        "-c",
        "user.email=tests@example.test",
        "commit",
        "-m",
        message,
    )


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
    assert (
        metadata["module_fingerprints"]["audit"]["helper.py"]
        == hashlib.sha256(up.read_bytes()).hexdigest()
    )
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


def test_source_only_upgrade_refuses_missing_immutable_ref(tmp_path):
    source, client = fixtures(tmp_path)
    incoming = source / "apps" / "audit" / "helper.py"
    incoming.write_text(incoming.read_text() + "# upstream fix\n")
    commit(source, "upstream fix")

    origin = client / "primarykit-origin.json"
    metadata = json.loads(origin.read_text())
    metadata["module_source_refs"].pop("audit")
    origin.write_text(json.dumps(metadata))
    commit(client, "simulate missing module ancestry")
    before = origin.read_bytes()
    target = client / "apps" / "audit" / "helper.py"
    old = target.read_bytes()

    with pytest.raises(ValueError, match="immutable source ancestry"):
        apply_three_way_updates(source=source, project=client)

    assert target.read_bytes() == old
    assert origin.read_bytes() == before


def test_source_only_upgrade_refuses_forged_ancestor_and_hash(tmp_path):
    source, client = fixtures(tmp_path)
    incoming = source / "apps" / "audit" / "helper.py"
    incoming.write_text(incoming.read_text() + "# upstream fix\n")
    commit(source, "upstream fix")

    origin = client / "primarykit-origin.json"
    metadata = json.loads(origin.read_text())
    metadata["module_source_refs"]["audit"] = git(client, "rev-parse", "HEAD")
    origin.write_text(json.dumps(metadata))
    commit(client, "simulate unrelated ancestry")
    with pytest.raises(ValueError, match="ancestry is not available"):
        apply_three_way_updates(source=source, project=client)

    metadata["module_source_refs"]["audit"] = git(source, "rev-parse", "HEAD")
    origin.write_text(json.dumps(metadata))
    commit(client, "simulate wrong historical baseline")
    with pytest.raises(ValueError, match="historical baseline does not match"):
        apply_three_way_updates(source=source, project=client)
    assert "# upstream fix" not in (client / "apps" / "audit" / "helper.py").read_text()


def test_three_successive_synthetic_source_revisions_preserve_client_edits(tmp_path):
    """Exercise three immutable source transitions, not published SemVer releases."""
    source, client = fixtures(tmp_path)
    incoming = source / "apps" / "audit" / "helper.py"
    target = client / "apps" / "audit" / "helper.py"

    target.write_text(target.read_text().replace("# original 2\n", "# client customization 2\n"))
    commit(client, "client customization before source updates")

    for number, line in enumerate((20, 40, 60), start=2):
        incoming.write_text(
            incoming.read_text().replace(
                f"# original {line}\n", f"# upstream revision {number} line {line}\n"
            )
        )
        commit(source, f"synthetic upstream revision {number}")
        result = apply_three_way_updates(source=source, project=client)
        assert result["applied"] is True
        assert result["updated"] == ["audit/helper.py"]
        text = target.read_text()
        assert "# client customization 2" in text
        for earlier, original_line in enumerate((20, 40, 60)[: number - 1], start=2):
            assert f"# upstream revision {earlier} line {original_line}" in text
        metadata = json.loads((client / "primarykit-origin.json").read_text())
        assert metadata["module_source_refs"]["audit"] == git(source, "rev-parse", "HEAD")
        assert (
            metadata["module_fingerprints"]["audit"]["helper.py"]
            == hashlib.sha256(incoming.read_bytes()).hexdigest()
        )
        commit(client, f"reviewed synthetic source update {number}")

    assert apply_three_way_updates(source=source, project=client)["applied"] is False


def test_three_way_apply_restores_all_files_if_provenance_write_fails(tmp_path, monkeypatch):
    source, client = fixtures(tmp_path)
    admin = client / "apps" / "audit" / "admin.py"
    helper = client / "apps" / "audit" / "helper.py"
    origin = client / "primarykit-origin.json"
    original = (admin.read_bytes(), helper.read_bytes(), origin.read_bytes())

    source_admin = source / "apps" / "audit" / "admin.py"
    source_admin.write_bytes(source_admin.read_bytes() + b"\n# upstream admin change\n")
    source_helper = source / "apps" / "audit" / "helper.py"
    source_helper.write_text(source_helper.read_text() + "# upstream helper change\n")
    commit(source, "two non-contract source changes")

    replace = apply_module_upgrade.os.replace

    def fail_commit(src, dst):
        if Path(dst) == origin and Path(src).name == "primarykit-origin.json":
            raise OSError("simulated provenance failure")
        return replace(src, dst)

    monkeypatch.setattr(apply_module_upgrade.os, "replace", fail_commit)
    with pytest.raises(OSError, match="simulated provenance failure"):
        apply_three_way_updates(source=source, project=client)

    assert (admin.read_bytes(), helper.read_bytes(), origin.read_bytes()) == original
    assert not list(client.glob(".primarykit-apply-*"))


def test_converged_file_ancestry_advances_with_related_upstream_change(tmp_path):
    """Already-accepted client bytes must not retain stale hashes after apply."""
    source, client = fixtures(tmp_path)
    upstream_helper = source / "apps" / "audit" / "helper.py"
    upstream_admin = source / "apps" / "audit" / "admin.py"
    client_admin = client / "apps" / "audit" / "admin.py"

    upstream_helper.write_text(upstream_helper.read_text() + "# upstream helper fix\n")
    upstream_admin.write_text(upstream_admin.read_text() + "\n# manually adopted revision one\n")
    commit(source, "two independent upstream edits")

    # The client independently accepted only admin.py, before invoking upgrade.
    client_admin.write_bytes(upstream_admin.read_bytes())
    commit(client, "manually accepted upstream admin change")
    first = apply_three_way_updates(source=source, project=client)
    assert first["updated"] == ["audit/helper.py"]

    origin = client / "primarykit-origin.json"
    metadata = json.loads(origin.read_text())
    assert (
        metadata["module_fingerprints"]["audit"]["admin.py"]
        == hashlib.sha256(upstream_admin.read_bytes()).hexdigest()
    )
    assert metadata["module_source_refs"]["audit"] == git(source, "rev-parse", "HEAD")
    commit(client, "reviewed first source update")

    # If admin.py retained the *old* fingerprint, this previously failed with
    # "historical baseline does not match" despite a genuine source ancestry.
    upstream_admin.write_text(upstream_admin.read_text() + "# upstream admin revision two\n")
    commit(source, "next admin revision")
    second = apply_three_way_updates(source=source, project=client)
    assert second["updated"] == ["audit/admin.py"]
    assert "# upstream admin revision two" in client_admin.read_text()


def test_converged_contract_changes_block_related_upgrade(tmp_path):
    """A byte-identical client contract is still a schema/behavior review."""
    source, client = fixtures(tmp_path)
    upstream_helper = source / "apps" / "audit" / "helper.py"
    upstream_contract = source / "apps" / "audit" / "services.py"
    client_contract = client / "apps" / "audit" / "services.py"

    upstream_helper.write_text(upstream_helper.read_text() + "# unrelated upstream helper\n")
    upstream_contract.write_text(upstream_contract.read_text() + "\n# changed contract\n")
    commit(source, "upstream helper and contract changed")
    client_contract.write_bytes(upstream_contract.read_bytes())
    commit(client, "manually copied new contract")
    origin = client / "primarykit-origin.json"
    previous = origin.read_bytes()

    with pytest.raises(ValueError, match="converged contract needs review"):
        apply_three_way_updates(source=source, project=client)
    assert origin.read_bytes() == previous
    assert (
        "# unrelated upstream helper" not in (client / "apps" / "audit" / "helper.py").read_text()
    )


def test_converged_file_rejects_forged_history(tmp_path):
    source, client = fixtures(tmp_path)
    upstream_helper = source / "apps" / "audit" / "helper.py"
    upstream_admin = source / "apps" / "audit" / "admin.py"
    client_admin = client / "apps" / "audit" / "admin.py"

    upstream_helper.write_text(upstream_helper.read_text() + "# upstream edit\n")
    upstream_admin.write_text(upstream_admin.read_text() + "\n# accepted edit\n")
    commit(source, "upstream revision")
    client_admin.write_bytes(upstream_admin.read_bytes())
    origin = client / "primarykit-origin.json"
    metadata = json.loads(origin.read_text())
    metadata["module_fingerprints"]["audit"]["admin.py"] = "0" * 64
    origin.write_text(json.dumps(metadata))
    commit(client, "manually accepted change with bad provenance")
    before = origin.read_bytes()

    with pytest.raises(ValueError, match="converged baseline mismatch"):
        apply_three_way_updates(source=source, project=client)
    assert origin.read_bytes() == before
