"""Source-only module scaffold: no writes on dry-run or unsafe requests."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import module_scaffold
from scripts.module_scaffold import (
    dependency_dot,
    dependency_graph,
    scaffold_module,
    validate_name,
)


@pytest.fixture
def kit_root(tmp_path):
    root = tmp_path / "source-kit"
    apps = root / "apps"
    apps.mkdir(parents=True)
    (apps / "__init__.py").write_text("")
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "new_project.py").write_text("# Source-catalog marker\n")
    for name, requires in (
        ("core", ()),
        ("notifications", ()),
        ("users", ("core", "notifications")),
    ):
        folder = apps / name
        folder.mkdir()
        (folder / "__init__.py").write_text("")
        (folder / "apps.py").write_text("# minimal Django app config\n")
        (folder / "manifest.py").write_text(
            "from apps.core.module_registry import Module\n"
            f'MODULE = Module(name="{name}", requires={requires!r})\n'
        )
    return root


@pytest.mark.parametrize(
    "name",
    ["", "Name", "my-app", "123name", "class", "a/b", "../escape", "a.b", "my name", "модуль"],
)
def test_scaffold_rejects_unsafe_module_names_without_writing(kit_root, name):
    with pytest.raises(ValueError, match="identifier"):
        scaffold_module(name, root=kit_root)
    assert sorted(path.name for path in (kit_root / "apps").iterdir()) == [
        "__init__.py",
        "core",
        "notifications",
        "users",
    ]


def test_scaffold_accepts_identifiers_with_underscores(kit_root):
    plan = scaffold_module("private_chat", root=kit_root, requires=("users",))
    assert plan["module"] == "private_chat"
    folder = kit_root / "apps" / "private_chat"
    assert sorted(
        path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()
    ) == [
        "__init__.py",
        "apps.py",
        "manifest.py",
        "tests/__init__.py",
        "tests/test_private_chat.py",
    ]
    apps_code = (folder / "apps.py").read_text()
    assert "class PrivateChatConfig(AppConfig):" in apps_code
    assert 'name = "apps.private_chat"' in apps_code
    assert "requires=('users',)" in (folder / "manifest.py").read_text()
    assert "migrations" not in {path.name for path in folder.iterdir()}
    assert "Route(" not in (folder / "manifest.py").read_text()
    assert "private_chat" in {module["name"] for module in dependency_graph(kit_root)["modules"]}


def test_scaffold_rolls_back_partial_creation_on_write_failure(kit_root, monkeypatch):
    original_open = Path.open

    def failing_open(path, *args, **kwargs):
        if path.parent.name == "retries" and path.name == "manifest.py":
            raise OSError("simulated disk error")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(OSError, match="disk error"):
        scaffold_module("retries", root=kit_root)
    assert not (kit_root / "apps" / "retries").exists()


def test_scaffold_dry_run_plans_without_writing(kit_root):
    plan = scaffold_module("reviews", root=kit_root, requires=("users",), dry_run=True)
    assert plan["dry_run"] is True
    assert plan["requires"] == ["users"]
    assert "apps/reviews/manifest.py" in plan["files"]
    assert not (kit_root / "apps" / "reviews").exists()


def test_scaffold_never_overwrites_existing_or_symlink(kit_root, tmp_path):
    first = scaffold_module("reviews", root=kit_root)
    original = (kit_root / "apps" / "reviews" / "manifest.py").read_bytes()
    with pytest.raises(FileExistsError):
        scaffold_module("reviews", root=kit_root)
    assert (kit_root / "apps" / "reviews" / "manifest.py").read_bytes() == original
    assert first["module"] == "reviews"

    outside = tmp_path / "unrelated"
    outside.mkdir()
    (outside / "sentinel").write_text("preserve")
    (kit_root / "apps" / "external").symlink_to(outside, target_is_directory=True)
    with pytest.raises(FileExistsError):
        scaffold_module("external", root=kit_root)
    assert (outside / "sentinel").read_text() == "preserve"


@pytest.mark.parametrize("requires", [("ghost",), ("users", "users"), ("new_app",), ("bad-name",)])
def test_scaffold_rejects_invalid_requirements(kit_root, requires):
    with pytest.raises(ValueError):
        scaffold_module("new_app", root=kit_root, requires=requires)
    assert not (kit_root / "apps" / "new_app").exists()


def test_graph_json_and_dot_are_deterministic_and_show_optional_edges(kit_root):
    folder = kit_root / "apps" / "core"
    (folder / "manifest.py").write_text(
        'from apps.core.module_registry import Module\n'
        'MODULE = Module(name="core", optional=("notifications", "absent_module"))\n'
    )
    graph = dependency_graph(kit_root)
    assert [m["name"] for m in graph["modules"]] == ["core", "notifications", "users"]
    assert json.loads(json.dumps(graph))["modules"][0]["optional"] == [
        "notifications",
        "absent_module",
    ]
    dot = dependency_dot(graph)
    assert dot == dependency_dot(dependency_graph(kit_root))
    assert '"users" -> "notifications" [style=solid];' in dot
    assert '"core" -> "notifications" [style=dashed];' in dot
    assert '"core" -> "absent_module"' not in dot


def test_graph_refuses_to_execute_manifest_code(kit_root, tmp_path):
    marker = tmp_path / "executed"
    manifest = kit_root / "apps" / "core" / "manifest.py"
    manifest.write_text(
        f"__import__('pathlib').Path({str(marker)!r}).write_text('unsafe')\n"
        'from apps.core.module_registry import Module\nMODULE = Module(name="core")\n'
    )
    assert dependency_graph(kit_root)["modules"][0]["name"] == "core"
    assert not marker.exists()
    manifest.write_text('MODULE = Module(name="core", requires=__import__("os").system("true"))\n')
    with pytest.raises((ValueError, TypeError)):
        dependency_graph(kit_root)
    assert not marker.exists()


def test_graph_rejects_missing_required_modules(kit_root):
    manifest = kit_root / "apps" / "core" / "manifest.py"
    manifest.write_text('MODULE = Module(name="core", requires=("absent",))\n')
    with pytest.raises(ValueError, match="missing dependencies"):
        dependency_graph(kit_root)


def test_graph_rejects_required_dependency_cycles(kit_root):
    (kit_root / "apps/core/manifest.py").write_text(
        'MODULE = Module(name="core", requires=("users",))\n'
    )
    with pytest.raises(ValueError, match="Cyclic required"):
        dependency_graph(kit_root)


def test_scaffold_only_runs_inside_source_catalog(kit_root):
    (kit_root / "scripts" / "new_project.py").unlink()
    with pytest.raises(ValueError, match="source checkout"):
        scaffold_module("new_module", root=kit_root, dry_run=True)
    with pytest.raises(ValueError, match="source checkout"):
        dependency_graph(kit_root)


def test_source_scaffold_doctor_and_manifest_registry_integration(kit_root):
    """A generated module must pass offline doctor and appear in runtime registry."""
    from scripts.module_scaffold import SOURCE_ROOT

    module_registry = SOURCE_ROOT / "apps/core/module_registry.py"
    doctor = SOURCE_ROOT / "apps/core/doctor.py"
    if not module_registry.is_file() or not doctor.is_file():
        pytest.skip("Full source checkout required for doctor/registry integration")
    shutil.copy2(module_registry, kit_root / "apps/core/module_registry.py")
    shutil.copy2(doctor, kit_root / "apps/core/doctor.py")
    settings = kit_root / "config/settings"
    settings.mkdir(parents=True)
    (settings / "base.py").write_text("# The source project is independent\n")
    (kit_root / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "0.1.0"\ndependencies = []\n'
    )
    (kit_root / "uv.lock").write_text(
        'version = 1\n[[package]]\nname = "fixture"\nversion = "0.1.0"\nsource = { virtual = "." }\n'
    )
    scaffold_module("reviews", root=kit_root, requires=("users",))
    shutil.rmtree(kit_root / "scripts")  # Simulates an independent generated backend.
    env = {**os.environ, "PYTHONPATH": str(kit_root)}
    doctor_result = subprocess.run(
        [sys.executable, "-m", "apps.core.doctor", "--strict", "--json"],
        cwd=kit_root, env=env, capture_output=True, text=True, check=False,
    )
    assert doctor_result.returncode == 0, doctor_result.stdout + doctor_result.stderr
    result = subprocess.run(
        [sys.executable, "-c", "from apps.core.module_registry import discover_modules, resolve_modules; "
         "modules=discover_modules(); assert 'reviews' in modules; "
         "assert modules['reviews'].requires == ('users',); "
         "resolve_modules(modules)"],
        cwd=kit_root, env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_cli_create_dry_run_and_graph_outputs(kit_root, monkeypatch, capsys):
    original_scaffold = scaffold_module
    original_graph = dependency_graph
    monkeypatch.setattr(
        module_scaffold,
        "scaffold_module",
        lambda name, *, requires, dry_run: original_scaffold(
            name, root=kit_root, requires=requires, dry_run=dry_run
        ),
    )
    monkeypatch.setattr(module_scaffold, "dependency_graph", lambda *args, **kwargs: original_graph(kit_root))
    assert module_scaffold.main(["create", "reviews", "--requires", "users", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert not (kit_root / "apps/reviews").exists()
    assert module_scaffold.main(["graph", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["modules"]
    assert module_scaffold.main(["graph", "--format", "dot"]) == 0
    assert capsys.readouterr().out.startswith("digraph primarykit_modules")


def test_validate_name_is_exact_and_deterministic():
    assert validate_name("my_module2") == "my_module2"
    with pytest.raises(ValueError):
        validate_name("__init__")
