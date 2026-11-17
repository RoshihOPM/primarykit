"""Apply modes take incoming module files from the source commit, not the worktree."""

import hashlib
import json
import subprocess

import pytest

from scripts.apply_module_upgrade import apply_three_way_updates
from scripts.module_upgrade import apply_safe_updates
from scripts.tests.test_three_way_apply import commit, fixtures, git

HELPER = "apps/audit/helper.py"


def blob(root, path: str) -> bytes:
    """Raw committed bytes, without eol or smudge filters."""
    return subprocess.run(
        ["git", "-C", str(root), "show", f"HEAD:{path}"], check=True, capture_output=True
    ).stdout


def provenance(client) -> dict:
    return json.loads((client / "primarykit-origin.json").read_text())


def ignore_local_hack(source):
    """Commit an ignore rule, then create a module file Git status never lists."""
    (source / ".gitignore").write_text("local_hack.py\n")
    helper = source / HELPER
    helper.write_text(helper.read_text() + "# upstream fix\n")
    commit(source, "upstream fix")
    (source / "apps" / "audit" / "local_hack.py").write_text("LOCAL_ONLY = True\n")
    assert git(source, "status", "--porcelain", "--", "apps") == ""


def crlf_upstream_change(source, old: str, new: str):
    """Commit an LF blob while the checked out file keeps CRLF line endings."""
    git(source, "config", "core.autocrlf", "true")
    helper = source / HELPER
    text = helper.read_bytes().decode().replace("\r\n", "\n").replace(old, new)
    helper.write_bytes(text.replace("\n", "\r\n").encode())
    commit(source, f"upstream {new}")
    assert git(source, "status", "--porcelain", "--", "apps") == ""
    assert b"\r\n" in helper.read_bytes()
    assert b"\r" not in blob(source, HELPER)


def assert_matches_source_commit(source, client):
    committed = blob(source, HELPER)
    assert (client / HELPER).read_bytes() == committed
    metadata = provenance(client)
    assert (
        metadata["module_fingerprints"]["audit"]["helper.py"]
        == hashlib.sha256(committed).hexdigest()
    )
    assert metadata["module_source_refs"]["audit"] == git(source, "rev-parse", "HEAD")


def test_three_way_apply_ignores_git_ignored_source_file(tmp_path):
    source, client = fixtures(tmp_path)
    ignore_local_hack(source)

    result = apply_three_way_updates(source=source, project=client)

    assert result["updated"] == ["audit/helper.py"]
    assert not (client / "apps" / "audit" / "local_hack.py").exists()
    assert "local_hack.py" not in provenance(client)["module_fingerprints"]["audit"]
    assert_matches_source_commit(source, client)


def test_apply_safe_ignores_git_ignored_source_file(tmp_path):
    source, client = fixtures(tmp_path)
    ignore_local_hack(source)

    result = apply_safe_updates(source=source, project=client)

    assert result == {"updated": ["audit/helper.py"], "applied": True}
    assert not (client / "apps" / "audit" / "local_hack.py").exists()
    assert "local_hack.py" not in provenance(client)["module_fingerprints"]["audit"]
    assert_matches_source_commit(source, client)


def test_three_way_apply_fingerprints_committed_bytes_across_line_ending_filters(tmp_path):
    source, client = fixtures(tmp_path)
    local = client / HELPER
    local.write_text(local.read_text().replace("# original 2\n", "# client 2\n"))
    commit(client, "client customization")

    for line in (40, 60):
        crlf_upstream_change(source, f"# original {line}\n", f"# upstream {line}\n")
        result = apply_three_way_updates(source=source, project=client)
        assert result["updated"] == ["audit/helper.py"]
        text = local.read_bytes()
        assert b"\r" not in text
        assert b"# client 2\n" in text
        assert f"# upstream {line}\n".encode() in text
        metadata = provenance(client)
        assert (
            metadata["module_fingerprints"]["audit"]["helper.py"]
            == hashlib.sha256(blob(source, HELPER)).hexdigest()
        )
        commit(client, f"reviewed upstream {line}")


def test_apply_safe_line_ending_filter_does_not_poison_later_three_way_upgrade(tmp_path):
    source, client = fixtures(tmp_path)
    crlf_upstream_change(source, "# original 40\n", "# upstream 40\n")

    assert apply_safe_updates(source=source, project=client)["applied"] is True
    assert_matches_source_commit(source, client)
    commit(client, "reviewed safe update")

    crlf_upstream_change(source, "# original 60\n", "# upstream 60\n")
    result = apply_three_way_updates(source=source, project=client)
    assert result["updated"] == ["audit/helper.py"]
    assert_matches_source_commit(source, client)


def test_apply_safe_uncommitted_source_never_advances_immutable_ancestry(tmp_path):
    source, client = fixtures(tmp_path)
    before = provenance(client)["module_source_refs"]["audit"]
    helper = source / HELPER
    helper.write_text(helper.read_text() + "# uncommitted\n")

    assert apply_safe_updates(source=source, project=client)["applied"] is True

    assert (client / HELPER).read_bytes() == helper.read_bytes()
    assert provenance(client)["module_source_refs"]["audit"] == before


def test_three_way_apply_blocks_committed_symlink(tmp_path):
    source, client = fixtures(tmp_path)
    helper = source / HELPER
    helper.write_text(helper.read_text() + "# upstream fix\n")
    (source / "apps" / "audit" / "linked.py").symlink_to(helper)
    commit(source, "committed symlink")
    with pytest.raises(ValueError, match="[Ss]ymlink"):
        apply_three_way_updates(source=source, project=client)
    assert "# upstream fix" not in (client / HELPER).read_text()
