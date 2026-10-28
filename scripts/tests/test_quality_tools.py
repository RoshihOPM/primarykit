"""Offline regression tests for opt-in, pinned code-quality tool installation."""

import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import quality_tools


def test_all_quality_tools_are_pinned_to_full_commits():
    assert set(quality_tools.TOOL_REVISIONS) == {"crapper", "dryer", "mutator"}
    assert all(
        re.fullmatch(r"[0-9a-f]{40}", sha)
        for sha in quality_tools.TOOL_REVISIONS.values()
    )


def test_quality_tool_verify_refuses_symlinked_install_root(tmp_path, monkeypatch):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / ".quality-tools"
    link.symlink_to(actual, target_is_directory=True)
    monkeypatch.setattr(quality_tools, "STORE", link)
    with pytest.raises(ValueError, match="symlinked"):
        quality_tools._verify_sources()


def test_quality_tool_run_refuses_uninstalled_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(quality_tools, "STORE", tmp_path / ".quality-tools")
    with pytest.raises(ValueError, match="not installed"):
        quality_tools.run_tool("mutator", ["--scan", "apps/core"])


def test_quality_tool_run_invokes_pinned_isolated_environment(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    venv = root / ".quality-tools" / "venv" / "bin"
    venv.mkdir(parents=True)
    python = venv / "python"
    python.write_text("")
    monkeypatch.setattr(quality_tools, "ROOT", root)
    monkeypatch.setattr(quality_tools, "STORE", root / ".quality-tools")
    monkeypatch.setattr(quality_tools, "_verify_sources", lambda: None)
    executions = []

    def fake_run(command, **kwargs):
        executions.append((command, kwargs))
        return SimpleNamespace(returncode=3)

    monkeypatch.setattr(quality_tools.subprocess, "run", fake_run)
    result = quality_tools.run_tool("mutator", ["--scan", "apps/orders/services.py"])
    assert result == 3
    assert executions == [
        (
            [str(python), "-m", "mutator", "--scan", "apps/orders/services.py"],
            {"check": False, "cwd": root},
        )
    ]


def test_quality_tool_installer_pins_three_clones_and_uses_uv(tmp_path, monkeypatch):
    store = tmp_path / ".quality-tools"
    monkeypatch.setattr(quality_tools, "STORE", store)
    monkeypatch.setattr(quality_tools.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(quality_tools, "_verify_sources", lambda: None)
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(quality_tools.subprocess, "run", fake_run)
    quality_tools.install()
    clones = [cmd for cmd in commands if cmd[:3] == ["git", "clone", "--quiet"]]
    checkouts = [cmd for cmd in commands if "checkout" in cmd]
    assert len(clones) == len(checkouts) == 3
    assert [cmd[-1] for cmd in checkouts] == list(quality_tools.TOOL_REVISIONS.values())
    assert commands[-2][:2] == ["uv", "venv"]
    assert commands[-1][:3] == ["uv", "pip", "install"]
    assert "--python" in commands[-1]
    assert all(str(store / name) in commands[-1] for name in quality_tools.TOOL_REVISIONS)


def test_quality_tool_main_checks_arguments_before_install(monkeypatch):
    monkeypatch.setattr(
        quality_tools, "install", lambda: pytest.fail("install must not be invoked")
    )
    with pytest.raises(SystemExit) as exc:
        quality_tools.main(["install", "--unexpected"])
    assert exc.value.code == 2


def test_quality_tool_verify_detects_dirty_source(tmp_path, monkeypatch):
    store = tmp_path / ".quality-tools"
    store.mkdir()
    for name in quality_tools.TOOL_REVISIONS:
        (store / name).mkdir()
    monkeypatch.setattr(quality_tools, "STORE", store)
    monkeypatch.setattr(quality_tools, "_git_revision", lambda folder: quality_tools.TOOL_REVISIONS[folder.name])
    def fake_run(command, **kwargs):
        return SimpleNamespace(stdout="?? unexpectedly-modified.py\n")
    monkeypatch.setattr(quality_tools.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="uncommitted"):
        quality_tools._verify_sources()
