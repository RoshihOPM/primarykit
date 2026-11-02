"""Regressions for module provenance hashes in relocated source checkouts."""

import hashlib
import subprocess

import pytest

from scripts.new_project import _module_fingerprints, _source_git_revision


@pytest.mark.parametrize("parent_name", ["tests", "migrations", "__pycache__"])
def test_provenance_ignores_only_module_local_excluded_paths(tmp_path, parent_name):
    # Users may clone PrimaryKit under a parent named tests or migrations.
    # Those names must not erase every digest in client provenance.
    root = tmp_path / parent_name / "primarykit"
    module = root / "apps" / "audit"
    (module / "nested").mkdir(parents=True)
    (module / "tests").mkdir()
    (module / "migrations").mkdir()
    (module / "__pycache__").mkdir()

    helper = module / "helper.py"
    helper.write_text("ANSWER = 42\n", encoding="utf-8")
    nested = module / "nested" / "service.py"
    nested.write_text("VALUE = 3\n", encoding="utf-8")
    (module / "tests" / "test_helper.py").write_text("untracked\n", encoding="utf-8")
    (module / "migrations" / "0001_initial.py").write_text("untracked\n", encoding="utf-8")
    (module / "__pycache__" / "cached.py").write_text("untracked\n", encoding="utf-8")

    fingerprints = _module_fingerprints(root, {"audit"})

    assert fingerprints == {
        "audit": {
            "helper.py": hashlib.sha256(helper.read_bytes()).hexdigest(),
            "nested/service.py": hashlib.sha256(nested.read_bytes()).hexdigest(),
        }
    }


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_git_provenance_requires_clean_module_tree(tmp_path):
    source = tmp_path / "checkout"
    (source / "apps" / "audit").mkdir(parents=True)
    helper = source / "apps" / "audit" / "helper.py"
    helper.write_text("ORIGINAL = True\n", encoding="utf-8")
    (source / "README.md").write_text("initial docs\n", encoding="utf-8")
    _git(source, "init", "-q")
    _git(source, "add", ".")
    _git(
        source,
        "-c",
        "user.name=PrimaryKit",
        "-c",
        "user.email=tests@example.test",
        "commit",
        "-m",
        "baseline",
    )
    revision = _git(source, "rev-parse", "HEAD")
    assert _source_git_revision(source) == revision

    # Docs-only edits do not change historical module bytes.
    (source / "README.md").write_text("edited docs\n", encoding="utf-8")
    assert _source_git_revision(source) == revision

    # A dirty tracked source module cannot claim the clean ancestor.
    helper.write_text("UNCOMMITTED = True\n", encoding="utf-8")
    assert _source_git_revision(source) is None
    helper.write_text("ORIGINAL = True\n", encoding="utf-8")

    # A newly added, untracked module file is also not part of HEAD.
    extra = source / "apps" / "audit" / "new_helper.py"
    extra.write_text("NEW = True\n", encoding="utf-8")
    assert _source_git_revision(source) is None
    extra.unlink()
    assert _source_git_revision(source) == revision


def test_git_provenance_rejects_parent_checkout_falsely_claimed_as_source(tmp_path):
    parent = tmp_path / "workspace"
    source = parent / "exported-source"
    (source / "apps").mkdir(parents=True)
    _git(parent, "init", "-q")
    (parent / "README.md").write_text("workspace\n", encoding="utf-8")
    _git(parent, "add", ".")
    _git(
        parent,
        "-c",
        "user.name=PrimaryKit",
        "-c",
        "user.email=tests@example.test",
        "commit",
        "-m",
        "workspace",
    )
    assert _source_git_revision(source) is None
