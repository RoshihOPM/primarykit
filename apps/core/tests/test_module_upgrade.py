import json

import pytest

from scripts.module_upgrade import compare_modules
from scripts.new_project import SOURCE_ROOT, create_project


def test_read_only_upgrade_report_detects_conflicts(tmp_path):
    target = create_project(tmp_path / "client", name="new-client", optional_apps={"audit"})
    report = compare_modules(source=SOURCE_ROOT, project=target)
    assert report["review_required"] is False

    file = target / "apps" / "audit" / "services.py"
    file.write_text(file.read_text(encoding="utf-8") + "\n# Client-only extension\n")
    local = compare_modules(source=SOURCE_ROOT, project=target)
    entry = next(
        item
        for item in local["modules"]["audit"]["changes"]
        if item["path"] == "services.py"
    )
    assert entry["change"] == "client_modified"
    assert entry["contract_review"] is True

    alternate = tmp_path / "source"
    (alternate / "apps" / "core").mkdir(parents=True)
    (alternate / "apps" / "core" / "manifest.py").write_text("source")
    (alternate / "apps" / "audit").mkdir(parents=True)
    (alternate / "apps" / "audit" / "services.py").write_text("new source contract")
    clash = compare_modules(source=alternate, project=target)
    found = next(
        item
        for item in clash["modules"]["audit"]["changes"]
        if item["path"] == "services.py"
    )
    assert found["change"] == "conflict_review"
    assert clash["review_required"]


def test_module_upgrade_refuses_unknown_baseline(tmp_path):
    target = create_project(tmp_path / "client", name="new-client")
    path = target / "primarykit-origin.json"
    metadata = json.loads(path.read_text())
    metadata.pop("module_fingerprints")
    path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="baseline"):
        compare_modules(source=SOURCE_ROOT, project=target)
