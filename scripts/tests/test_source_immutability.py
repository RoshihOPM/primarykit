"""Upgrade apply modes only trust module bytes that exist in the source commit."""

import json

import pytest

from scripts.apply_module_upgrade import apply_three_way_updates
from scripts.module_upgrade import apply_safe_updates, source_differs_from_commit
from scripts.tests.test_three_way_apply import commit, fixtures, git


def test_git_ignored_source_file_is_never_copied_or_fingerprinted(tmp_path):
    source, client = fixtures(tmp_path)
    helper = source / "apps" / "audit" / "helper.py"
    helper.write_text(helper.read_text() + "# upstream\n")
    (source / ".gitignore").write_text((source / ".gitignore").read_text() + "\nlocal_hack.py\n")
    commit(source, "upstream helper")
    (source / "apps" / "audit" / "local_hack.py").write_text("SECRET_LOCAL_EXPERIMENT = True\n")
    assert git(source, "status", "--porcelain", "--", "apps") == ""
    before = (client / "primarykit-origin.json").read_bytes()

    with pytest.raises(ValueError, match="not an immutable checkout.*local_hack.py"):
        apply_three_way_updates(source=source, project=client)

    assert not (client / "apps" / "audit" / "local_hack.py").exists()
    assert (client / "primarykit-origin.json").read_bytes() == before
    assert git(client, "status", "--porcelain") == ""


def test_filtered_line_endings_do_not_count_as_committed_bytes(tmp_path):
    source, client = fixtures(tmp_path)
    helper = source / "apps" / "audit" / "helper.py"
    helper.write_text(helper.read_text() + "# upstream\n")
    commit(source, "upstream helper")
    git(source, "config", "core.autocrlf", "input")
    helper.write_bytes(helper.read_bytes().replace(b"\n", b"\r\n"))
    git(source, "add", "apps")  # The filter normalizes CRLF, so Git sees no change.
    assert git(source, "status", "--porcelain", "--", "apps") == ""

    assert source_differs_from_commit(source, ["audit"]) == [
        "audit/helper.py: differs from the committed blob"
    ]
    with pytest.raises(ValueError, match="not an immutable checkout"):
        apply_three_way_updates(source=source, project=client)
    assert b"\r\n" not in (client / "apps" / "audit" / "helper.py").read_bytes()


def test_clean_committed_source_is_accepted(tmp_path):
    source, client = fixtures(tmp_path)
    helper = source / "apps" / "audit" / "helper.py"
    helper.write_text(helper.read_text() + "# upstream\n")
    commit(source, "upstream helper")

    assert source_differs_from_commit(source, ["audit", "core", "users"]) == []
    assert apply_three_way_updates(source=source, project=client)["updated"] == ["audit/helper.py"]


def test_apply_safe_does_not_anchor_ancestry_to_ignored_source_bytes(tmp_path):
    source, client = fixtures(tmp_path)
    (source / ".gitignore").write_text((source / ".gitignore").read_text() + "\nlocal_hack.py\n")
    commit(source, "ignore rule")
    old_ref = json.loads((client / "primarykit-origin.json").read_text())["module_source_refs"][
        "audit"
    ]
    (source / "apps" / "audit" / "local_hack.py").write_text("LOCAL = True\n")

    apply_safe_updates(source=source, project=client)

    refs = json.loads((client / "primarykit-origin.json").read_text())["module_source_refs"]
    assert refs["audit"] == old_ref != git(source, "rev-parse", "HEAD")
