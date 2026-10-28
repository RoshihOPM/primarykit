"""Regressions for module provenance hashes in relocated source checkouts."""

import hashlib

import pytest

from scripts.new_project import _module_fingerprints


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
