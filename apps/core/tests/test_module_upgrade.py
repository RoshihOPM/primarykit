import hashlib
import json

import pytest
from django.conf import settings
from django.core.management.base import CommandError

from apps.core.doctor import inspect_project
from apps.core.management.commands import install_kit_module
from scripts.module_upgrade import apply_safe_updates, compare_modules, three_way_plan
from scripts.new_project import SOURCE_ROOT, create_project


def test_read_only_upgrade_report_detects_conflicts(tmp_path):
    target = create_project(tmp_path / "client", name="new-client", optional_apps={"audit"})
    report = compare_modules(source=SOURCE_ROOT, project=target)
    assert report["review_required"] is False

    file = target / "apps" / "audit" / "services.py"
    file.write_text(file.read_text(encoding="utf-8") + "\n# Client-only extension\n")
    local = compare_modules(source=SOURCE_ROOT, project=target)
    entry = next(
        item for item in local["modules"]["audit"]["changes"] if item["path"] == "services.py"
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
        item for item in clash["modules"]["audit"]["changes"] if item["path"] == "services.py"
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


@pytest.mark.parametrize(
    ("module", "added"),
    [
        ("audit", {"audit"}),
        ("privacy", {"audit", "tasks", "privacy"}),
    ],
)
def test_install_kit_module_records_trusted_baselines_and_reports_clean(
    tmp_path, monkeypatch, module, added
):
    target = create_project(tmp_path / "client", name="new-client")
    monkeypatch.setattr(settings, "BASE_DIR", target)
    command = install_kit_module.Command()

    before = (target / "primarykit-origin.json").read_text(encoding="utf-8")
    command.handle(module=module, source=SOURCE_ROOT, dry_run=True)
    assert (target / "primarykit-origin.json").read_text(encoding="utf-8") == before
    assert not (target / "apps" / module).exists()

    command.handle(module=module, source=SOURCE_ROOT, dry_run=False)
    metadata = json.loads((target / "primarykit-origin.json").read_text(encoding="utf-8"))
    for name in added:
        assert name in metadata["included_apps"]
        expected = hashlib.sha256((target / "apps" / name / "manifest.py").read_bytes())
        assert metadata["module_fingerprints"][name]["manifest.py"] == expected.hexdigest()
    assert not inspect_project(target).failed(strict=True)
    assert compare_modules(source=SOURCE_ROOT, project=target)["review_required"] is False


def test_install_kit_module_rejects_corrupt_provenance_without_copy(tmp_path, monkeypatch):
    target = create_project(tmp_path / "client", name="new-client")
    monkeypatch.setattr(settings, "BASE_DIR", target)
    origin = target / "primarykit-origin.json"
    origin.write_text("{bad json", encoding="utf-8")

    with pytest.raises(CommandError, match="provenance"):
        install_kit_module.Command().handle(module="audit", source=SOURCE_ROOT, dry_run=False)
    assert origin.read_text(encoding="utf-8") == "{bad json"
    assert not (target / "apps" / "audit").exists()


def test_install_kit_module_rolls_back_when_metadata_replace_fails(tmp_path, monkeypatch):
    target = create_project(tmp_path / "client", name="new-client")
    monkeypatch.setattr(settings, "BASE_DIR", target)
    origin = target / "primarykit-origin.json"
    initial = origin.read_bytes()

    def refuse_replace(*_args):
        raise OSError("simulated metadata write failure")

    monkeypatch.setattr(install_kit_module.os, "replace", refuse_replace)
    with pytest.raises(CommandError, match="installation failed"):
        install_kit_module.Command().handle(module="privacy", source=SOURCE_ROOT, dry_run=False)
    assert origin.read_bytes() == initial
    for name in ("audit", "tasks", "privacy"):
        assert not (target / "apps" / name).exists()


def test_upgrade_report_warns_instead_of_guessing_missing_module_baseline(tmp_path):
    target = create_project(tmp_path / "client", name="new-client", optional_apps={"audit"})
    origin = target / "primarykit-origin.json"
    metadata = json.loads(origin.read_text(encoding="utf-8"))
    del metadata["module_fingerprints"]["audit"]
    origin.write_text(json.dumps(metadata), encoding="utf-8")

    report = compare_modules(source=SOURCE_ROOT, project=target)
    assert report["review_required"] is True
    assert report["modules"]["audit"]["changes"][0]["change"] == "baseline_unknown"
    assert report["modules"]["audit"]["changes"][0]["contract_review"] is True


def test_install_without_optional_origin_file(tmp_path, monkeypatch):
    target = create_project(tmp_path / "client", name="new-client")
    monkeypatch.setattr(settings, "BASE_DIR", target)
    origin = target / "primarykit-origin.json"
    origin.unlink()

    install_kit_module.Command().handle(module="audit", source=SOURCE_ROOT, dry_run=False)
    assert (target / "apps" / "audit" / "manifest.py").is_file()
    assert not origin.exists()


def test_apply_safe_update_copies_new_helper_and_advances_baseline(tmp_path):
    source = create_project(tmp_path / "source", name="source-api", optional_apps={"audit"})
    client = create_project(tmp_path / "client", name="client-api", optional_apps={"audit"})
    helper = source / "apps" / "audit" / "helpers.py"
    helper.write_text("def safe_helper():\n    return True\n", encoding="utf-8")

    plan = compare_modules(source=source, project=client)
    assert plan["modules"]["audit"]["changes"] == [
        {
            "path": "helpers.py",
            "change": "source_update",
            "contract_review": False,
            "source_deleted": False,
            "client_deleted": True,
        }
    ]
    result = apply_safe_updates(source=source, project=client)
    assert result == {"updated": ["audit/helpers.py"], "applied": True}
    assert (client / "apps" / "audit" / "helpers.py").read_bytes() == helper.read_bytes()
    assert compare_modules(source=source, project=client)["review_required"] is False
    assert apply_safe_updates(source=source, project=client)["applied"] is False


def test_apply_safe_update_refuses_contract_and_preserves_client(tmp_path):
    source = create_project(tmp_path / "source", name="source-api", optional_apps={"audit"})
    client = create_project(tmp_path / "client", name="client-api", optional_apps={"audit"})
    service = source / "apps" / "audit" / "services.py"
    service.write_text(service.read_text(encoding="utf-8") + "\n# Security fix\n")
    origin = client / "primarykit-origin.json"
    before = origin.read_bytes()
    with pytest.raises(ValueError, match="Manual review required"):
        apply_safe_updates(source=source, project=client)
    assert origin.read_bytes() == before
    assert (client / "apps" / "audit" / "services.py").read_bytes() != service.read_bytes()


def test_apply_safe_update_refuses_client_conflict_and_source_deletion(tmp_path):
    source = create_project(tmp_path / "source", name="source-api", optional_apps={"audit"})
    client = create_project(tmp_path / "client", name="client-api", optional_apps={"audit"})
    (source / "apps" / "audit" / "helpers.py").write_text("source\n")
    (client / "apps" / "audit" / "helpers.py").write_text("client\n")
    with pytest.raises(ValueError, match="Manual review required"):
        apply_safe_updates(source=source, project=client)
    (client / "apps" / "audit" / "helpers.py").unlink()
    (source / "apps" / "audit" / "services.py").unlink()
    with pytest.raises(ValueError, match="Manual review required"):
        apply_safe_updates(source=source, project=client)
    assert not (client / "apps" / "audit" / "helpers.py").exists()


def test_apply_safe_update_refuses_untracked_source_migration(tmp_path):
    source = create_project(tmp_path / "source", name="source-api", optional_apps={"audit"})
    client = create_project(tmp_path / "client", name="client-api", optional_apps={"audit"})
    (source / "apps" / "audit" / "helpers.py").write_text("new helper\n")
    migrations = source / "apps" / "audit" / "migrations"
    migrations.mkdir()
    (migrations / "0001_initial.py").write_text("# Requires schema review\n")
    with pytest.raises(ValueError, match="migrations: manual schema review"):
        apply_safe_updates(source=source, project=client)
    assert not (client / "apps" / "audit" / "helpers.py").exists()


def test_three_way_plan_reports_unavailable_source_ref_without_modifying_client(tmp_path):
    source = create_project(tmp_path / "source", name="source-api", optional_apps={"audit"})
    client = create_project(tmp_path / "client", name="client-api", optional_apps={"audit"})
    helper = source / "apps" / "audit" / "helpers.py"
    helper.write_text("def updated():\n    return True\n")
    target = client / "apps" / "audit" / "helpers.py"
    target.write_text("def local():\n    return True\n")
    before = target.read_bytes()
    report = three_way_plan(source=source, project=client)
    assert report["all_mergeable"] is False
    assert report["candidates"][0]["reason"] in {
        "source_commit_unavailable",
        "missing_immutable_baseline",
    }
    assert target.read_bytes() == before


def test_apply_safe_update_rolls_back_all_files_on_provenance_failure(tmp_path, monkeypatch):
    """A failed commit of origin metadata must not leave half-upgraded modules."""
    from pathlib import Path

    from scripts import module_upgrade

    source = create_project(tmp_path / "source", name="source-api", optional_apps={"audit"})
    client = create_project(tmp_path / "client", name="client-api", optional_apps={"audit"})
    origin = client / "primarykit-origin.json"
    original_origin = origin.read_bytes()
    admin = client / "apps" / "audit" / "admin.py"
    original_admin = admin.read_bytes()

    incoming_admin = source / "apps" / "audit" / "admin.py"
    incoming_admin.write_bytes(incoming_admin.read_bytes() + b"\n# Upstream update\n")
    (source / "apps" / "audit" / "helpers.py").write_text("NEW_HELPER = True\n")
    actual_replace = module_upgrade.os.replace

    def fail_provenance_commit(src, dst):
        if Path(dst) == origin and Path(src).name == "primarykit-origin.json":
            raise OSError("provenance commit failed")
        return actual_replace(src, dst)

    monkeypatch.setattr(module_upgrade.os, "replace", fail_provenance_commit)
    with pytest.raises(OSError, match="provenance commit failed"):
        apply_safe_updates(source=source, project=client)

    assert origin.read_bytes() == original_origin
    assert admin.read_bytes() == original_admin
    assert not (client / "apps" / "audit" / "helpers.py").exists()
    assert not list(client.glob(".primarykit-upgrade-*"))



@pytest.mark.parametrize("side", ["source", "client"])
@pytest.mark.parametrize("entry_kind", ["file", "directory", "module"])
def test_upgrade_report_rejects_symlinked_module_paths(tmp_path, side, entry_kind):
    source = create_project(tmp_path / "source", name="source-api", optional_apps={"audit"})
    client = create_project(tmp_path / "client", name="client-api", optional_apps={"audit"})
    root = source if side == "source" else client
    external = tmp_path / "external"
    external.mkdir()

    if entry_kind == "module":
        module = root / "apps" / "audit"
        replacement = external / "audit"
        replacement.mkdir()
        module.rename(root / "apps" / "old_audit")
        module.symlink_to(replacement, target_is_directory=True)
    elif entry_kind == "directory":
        (root / "apps" / "audit" / "linked_dir").symlink_to(external, target_is_directory=True)
    else:
        sensitive = external / "secret.py"
        sensitive.write_text("SECRET_VALUE = 'must not be read'\n")
        (root / "apps" / "audit" / "linked.py").symlink_to(sensitive)

    with pytest.raises(ValueError, match="[Ss]ymlink"):
        compare_modules(source=source, project=client)


@pytest.mark.parametrize("side", ["source", "client"])
def test_upgrade_report_rejects_symlinked_apps_root(tmp_path, side):
    source = create_project(tmp_path / "source", name="source-api", optional_apps={"audit"})
    client = create_project(tmp_path / "client", name="client-api", optional_apps={"audit"})
    root = source if side == "source" else client
    apps = root / "apps"
    moved = root / "actual_apps"
    apps.rename(moved)
    apps.symlink_to(moved, target_is_directory=True)

    with pytest.raises(ValueError, match="Symlinked apps"):
        compare_modules(source=source, project=client)
