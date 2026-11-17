import hashlib
import json
import shutil
import subprocess
from io import StringIO

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


@pytest.mark.parametrize("contract", ["models.py", "services.py", "permissions.py", "views.py"])
def test_upgrade_nested_contract_files_require_review(tmp_path, contract):
    source = create_project(tmp_path / "source", name="source-api", optional_apps={"audit"})
    client = create_project(tmp_path / "client", name="client-api", optional_apps={"audit"})
    nested = source / "apps" / "audit" / "internal"
    nested.mkdir()
    (nested / contract).write_text("# sensitive nested contract\n", encoding="utf-8")
    safe = source / "apps" / "audit" / "helper.py"
    safe.write_text("# safe helper\n", encoding="utf-8")

    report = compare_modules(source=source, project=client)
    changes = {item["path"]: item for item in report["modules"]["audit"]["changes"]}
    assert changes[f"internal/{contract}"]["change"] == "source_update"
    assert changes[f"internal/{contract}"]["contract_review"] is True
    assert changes["helper.py"]["contract_review"] is False

    with pytest.raises(ValueError, match="Manual review required"):
        apply_safe_updates(source=source, project=client)
    assert not (client / "apps" / "audit" / "internal" / contract).exists()
    assert not (client / "apps" / "audit" / "helper.py").exists()


def _kit_module(source, name, *, manifest_extra="", migrations=False):
    """A minimal kit module that is only ever copied, never imported."""
    folder = source / "apps" / name
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text("")
    (folder / "apps.py").write_text("# portable module\n")
    (folder / "manifest.py").write_text(
        "from apps.core.module_registry import Module\n"
        f'MODULE = Module(name="{name}"{manifest_extra})\n'
    )
    if migrations:
        (folder / "migrations").mkdir()
        (folder / "migrations" / "__init__.py").write_text("")
        (folder / "migrations" / "0001_initial.py").write_text("# source history\n")
    pyproject = source / "pyproject.toml"
    if not pyproject.exists():
        pyproject.write_text('[project]\nname = "kit"\nversion = "9.9.9"\n')
    return folder


def _git(root, *args) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def _commit_kit(root) -> str:
    if shutil.which("git") is None:
        # The runtime container image ships without Git; the host CI run covers these.
        pytest.skip("Git is required to build a committed source checkout")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    identity = ("-c", "user.name=kit", "-c", "user.email=kit@example.invalid")
    _git(root, *identity, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "kit")
    return _git(root, "rev-parse", "HEAD")


def _client(tmp_path, monkeypatch):
    target = create_project(tmp_path / "client", name="new-client")
    monkeypatch.setattr(settings, "BASE_DIR", target)
    return target


def _install(source, module="extra") -> str:
    out = StringIO()
    install_kit_module.Command(stdout=out).handle(module=module, source=source, dry_run=False)
    return out.getvalue()


def _origin(target) -> dict:
    return json.loads((target / "primarykit-origin.json").read_text(encoding="utf-8"))


def _assert_nothing_installed(target, before, *names):
    assert (target / "primarykit-origin.json").read_bytes() == before
    for name in names:
        assert not (target / "apps" / name).exists()
    assert not list(target.glob(".primarykit-install-*"))


@pytest.mark.parametrize("dry_run", [True, False])
def test_install_kit_module_rejects_manifest_unknown_to_client_core(tmp_path, monkeypatch, dry_run):
    """A newer kit manifest field would break Django startup in an older client."""
    target = _client(tmp_path, monkeypatch)
    before = (target / "primarykit-origin.json").read_bytes()
    source = tmp_path / "kit"
    _kit_module(source, "base")
    _kit_module(source, "extra", manifest_extra=', requires=("base",), future_field=("x",)')

    with pytest.raises(CommandError, match=r"apps/extra/manifest\.py.*[Uu]pgrade.*apps/core"):
        install_kit_module.Command().handle(module="extra", source=source, dry_run=dry_run)
    _assert_nothing_installed(target, before, "base", "extra")


def test_install_kit_module_strips_non_bundled_migrations(tmp_path, monkeypatch):
    target = _client(tmp_path, monkeypatch)
    source = tmp_path / "kit"
    _kit_module(source, "extra", manifest_extra=', migration_policy="client"', migrations=True)
    _kit_module(source, "plain", migrations=True)  # default policy: none

    message = _install(source)
    plain_message = _install(source, module="plain")
    assert (target / "apps" / "extra" / "manifest.py").is_file()
    assert not (target / "apps" / "extra" / "migrations").exists()
    assert not (target / "apps" / "plain" / "migrations").exists()
    policies = _origin(target)["module_migration_policies"]
    assert (policies["extra"], policies["plain"]) == ("client", "none")
    assert "makemigrations extra" in message
    assert "makemigrations" not in plain_message


def test_install_kit_module_copies_bundled_history_and_reports_it(tmp_path, monkeypatch):
    target = _client(tmp_path, monkeypatch)
    source = tmp_path / "kit"
    _kit_module(source, "base", manifest_extra=', migration_policy="client"')
    _kit_module(
        source,
        "extra",
        manifest_extra=', requires=("base",), migration_policy="bundled"',
        migrations=True,
    )
    pinned = _origin(target)["module_migration_policies"]

    message = _install(source)
    history = target / "apps" / "extra" / "migrations" / "0001_initial.py"
    assert history.read_text() == "# source history\n"
    assert _origin(target)["module_migration_policies"] == pinned | {
        "base": "client",
        "extra": "bundled",
    }
    assert "makemigrations base;" in message
    assert "Bundled history shipped for: extra" in message


def test_install_kit_module_refuses_bundled_module_without_history(tmp_path, monkeypatch):
    target = _client(tmp_path, monkeypatch)
    before = (target / "primarykit-origin.json").read_bytes()
    source = tmp_path / "kit"
    folder = _kit_module(source, "extra", manifest_extra=', migration_policy="bundled"')
    (folder / "migrations").mkdir()
    (folder / "migrations" / "__init__.py").write_text("")

    with pytest.raises(CommandError, match="Bundled migrations missing for extra"):
        _install(source)
    _assert_nothing_installed(target, before, "extra")


@pytest.mark.parametrize("entry_kind", ["file", "directory", "module", "bundled_migration"])
def test_install_kit_module_rejects_source_symlinks_without_copy(tmp_path, monkeypatch, entry_kind):
    target = _client(tmp_path, monkeypatch)
    before = (target / "primarykit-origin.json").read_bytes()
    source = tmp_path / "kit"
    external = tmp_path / "external"
    external.mkdir()
    secret = external / "secret.py"
    secret.write_text("SECRET_VALUE = 'must not be copied'\n")
    bundled = entry_kind == "bundled_migration"
    folder = _kit_module(
        source,
        "extra",
        manifest_extra=', migration_policy="bundled"' if bundled else "",
        migrations=bundled,
    )
    if entry_kind == "file":
        (folder / "linked.py").symlink_to(secret)
    elif entry_kind == "directory":
        (folder / "linked_dir").symlink_to(external, target_is_directory=True)
    elif entry_kind == "bundled_migration":
        (folder / "migrations" / "0002_linked.py").symlink_to(secret)
    else:
        folder.rename(external / "extra")
        folder.symlink_to(external / "extra", target_is_directory=True)

    with pytest.raises(CommandError, match="[Ss]ymlink"):
        _install(source)
    _assert_nothing_installed(target, before, "extra")


def test_install_kit_module_ignores_symlink_inside_stripped_client_migrations(
    tmp_path, monkeypatch
):
    """Like the generator: paths that are never copied cannot block installation."""
    target = _client(tmp_path, monkeypatch)
    source = tmp_path / "kit"
    folder = _kit_module(
        source, "extra", manifest_extra=', migration_policy="client"', migrations=True
    )
    (folder / "migrations" / "0002_linked.py").symlink_to(folder / "apps.py")

    _install(source)
    assert not (target / "apps" / "extra" / "migrations").exists()


def _source_ref(target, name="extra"):
    metadata = _origin(target)
    assert name in metadata["included_apps"]
    assert metadata["module_versions"][name] == "9.9.9"
    return metadata["module_source_refs"].get(name)


def test_install_kit_module_records_source_ref_for_clean_git_root(tmp_path, monkeypatch):
    target = _client(tmp_path, monkeypatch)
    source = tmp_path / "kit"
    _kit_module(source, "extra", manifest_extra=', migration_policy="bundled"', migrations=True)
    _kit_module(source, "other")
    head = _commit_kit(source)
    # Dirt in a module that is not copied does not taint the copied one.
    (source / "apps" / "other" / "apps.py").write_text("# local edit\n")

    _install(source)
    assert _source_ref(target) == head


@pytest.mark.parametrize(
    "taint",
    ["no_git", "modified", "untracked", "ignored", "nested_root", "hidden_edit", "deleted"],
)
def test_install_kit_module_installs_untrusted_source_without_source_ref(
    tmp_path, monkeypatch, taint
):
    """HEAD is not an immutable ancestor of bytes that were never committed."""
    target = _client(tmp_path, monkeypatch)
    repository = tmp_path / "kit"
    source = repository / "nested" if taint == "nested_root" else repository
    folder = _kit_module(source, "extra")
    (folder / "helpers.py").write_text("COMMITTED = True\n")
    if taint == "ignored":
        (repository / ".gitignore").write_text("local_*.py\n")
    if taint != "no_git":
        _commit_kit(repository)
    if taint == "hidden_edit":
        _git(source, "update-index", "--assume-unchanged", "apps/extra/apps.py")
    if taint in {"modified", "hidden_edit"}:
        (folder / "apps.py").write_text("# uncommitted edit\n")
    elif taint == "untracked":
        (folder / "extra_helpers.py").write_text("UNTRACKED = True\n")
    elif taint == "ignored":
        (folder / "local_settings.py").write_text("IGNORED = True\n")
    elif taint == "deleted":
        (folder / "helpers.py").unlink()

    _install(source)
    assert (target / "apps" / "extra" / "manifest.py").is_file()
    assert _source_ref(target) is None


def test_install_kit_module_refuses_stale_migration_policy_pin(tmp_path, monkeypatch):
    """Never overwrite a recorded per-module history decision."""
    target = _client(tmp_path, monkeypatch)
    origin = target / "primarykit-origin.json"
    metadata = _origin(target)
    metadata["module_migration_policies"]["extra"] = "client"
    origin.write_text(json.dumps(metadata), encoding="utf-8")
    before = origin.read_bytes()
    source = tmp_path / "kit"
    _kit_module(source, "extra", manifest_extra=', migration_policy="bundled"', migrations=True)

    with pytest.raises(CommandError, match="already names a module"):
        _install(source)
    _assert_nothing_installed(target, before, "extra")


def test_install_kit_module_adds_policy_map_to_older_provenance(tmp_path, monkeypatch):
    target = _client(tmp_path, monkeypatch)
    origin = target / "primarykit-origin.json"
    metadata = _origin(target)
    del metadata["module_migration_policies"]
    origin.write_text(json.dumps(metadata), encoding="utf-8")
    source = tmp_path / "kit"
    _kit_module(source, "extra", manifest_extra=', migration_policy="client"')

    _install(source)
    assert _origin(target)["module_migration_policies"] == {"extra": "client"}


def test_install_without_origin_file_still_applies_copy_rules(tmp_path, monkeypatch):
    target = _client(tmp_path, monkeypatch)
    (target / "primarykit-origin.json").unlink()
    source = tmp_path / "kit"
    _kit_module(source, "extra", manifest_extra=', migration_policy="client"', migrations=True)

    assert "makemigrations extra" in _install(source)
    assert not (target / "apps" / "extra" / "migrations").exists()
    assert not (target / "primarykit-origin.json").exists()
