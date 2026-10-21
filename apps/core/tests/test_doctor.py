"""Doctor is copied with Core and runs without importing Django or the source kit."""

import json
import subprocess
import sys

from apps.core.doctor import inspect_project
from scripts.new_project import create_project


def _project(tmp_path, apps=frozenset()):
    return create_project(
        tmp_path / "customer-backend", name="customer-backend", optional_apps=set(apps)
    )


def test_offline_doctor_checks_generated_projects(tmp_path):
    target = _project(tmp_path, {"inventory", "catalog", "organizations", "statistics"})
    report = inspect_project(target)
    assert not report.findings
    assert {"core", "users", "notifications", "inventory"} <= set(report.modules)
    run = subprocess.run(
        [sys.executable, "-m", "apps.core.doctor", "--json", "--strict"],
        cwd=target,
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr + run.stdout
    assert json.loads(run.stdout)["ok"] is True
    assert "customer-backend" in (target / "pyproject.toml").read_text()


def test_offline_doctor_does_not_require_provenance_or_kit_checkout(tmp_path):
    target = _project(tmp_path, {"orders"})
    (target / "primarykit-origin.json").unlink()
    assert not inspect_project(target).failed()
    # A generated client's Python runtime must have no dependency on source scripts.
    assert not (target / "scripts").exists()
    assert not (target / "primarykit").exists()


def test_doctor_reports_missing_dependency_and_tenant_schema_mismatch(tmp_path):
    target = _project(tmp_path, {"inventory"})
    base = target / "config/settings/base.py"
    base.write_text(
        base.read_text().replace('INVENTORY_MODE = "standalone"', 'INVENTORY_MODE = "tenant"')
    )
    (target / "apps/notifications/manifest.py").unlink()
    codes = {item.code for item in inspect_project(target).findings}
    assert "baseline_missing" in codes
    assert "dependency_missing" in codes
    assert "tenant_dependency_missing" in codes


def test_doctor_rejects_runtime_kit_import_and_package_dependency(tmp_path):
    target = _project(tmp_path)
    (target / "config" / "from_kit.py").write_text("from primarykit import runtime\n")
    pyproject = target / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text().replace(
            '  "django>=6.1,<6.2",', '  "primarykit>=0.1",\n  "django>=6.1,<6.2",'
        )
    )
    report = inspect_project(target)
    assert report.failed()
    assert {"kit_import", "kit_dependency"} <= {item.code for item in report.findings}


def test_doctor_requires_matching_uv_lock(tmp_path):
    target = _project(tmp_path)
    lock_path = target / "uv.lock"
    source = lock_path.read_text()
    assert 'name = "customer-backend"' in source
    lock_path.write_text(source.replace('name = "customer-backend"', 'name = "wrong-backend"', 1))
    assert "lock_root_mismatch" in {item.code for item in inspect_project(target).findings}

    lock_path.unlink()
    assert "lock_missing" in {item.code for item in inspect_project(target).findings}


def test_doctor_stale_metadata_is_warning_and_strict_fails(tmp_path):
    target = _project(tmp_path)
    metadata = target / "primarykit-origin.json"
    source = json.loads(metadata.read_text())
    source["included_apps"] = ["core"]
    metadata.write_text(json.dumps(source))
    report = inspect_project(target)
    assert [item.code for item in report.findings] == ["origin_stale"]
    assert not report.failed()
    assert report.failed(strict=True)


def test_doctor_denies_changed_pinned_schema_after_generation(tmp_path):
    target = _project(tmp_path, {"catalog", "inventory", "organizations"})
    provenance = json.loads((target / "primarykit-origin.json").read_text())
    assert provenance["schema_modes"] == {"catalog": "tenant", "inventory": "tenant"}
    base = target / "config/settings/base.py"
    base.write_text(base.read_text().replace('CATALOG_MODE = "tenant"', 'CATALOG_MODE = "standalone"'))
    findings = {item.code for item in inspect_project(target).findings}
    assert "schema_mode_changed" in findings
    assert inspect_project(target).failed()


def test_schema_pin_does_not_break_older_clients_without_metadata(tmp_path):
    target = _project(tmp_path, {"catalog"})
    origin = target / "primarykit-origin.json"
    metadata = json.loads(origin.read_text())
    del metadata["schema_modes"]
    origin.write_text(json.dumps(metadata))
    assert not inspect_project(target).failed()
