"""CLI and TypeScript client generation regression tests (offline, no Node install)."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.core import cli, typescript_sdk


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "backend"
    project.mkdir()
    (project / "manage.py").write_text("", encoding="utf-8")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text('{"name":"demo","private":true}', encoding="utf-8")
    return project, frontend


def test_cli_new_delegates_to_source_generator_without_mutating(tmp_path, monkeypatch):
    script = tmp_path / "scripts" / "new_project.py"
    script.parent.mkdir()
    script.touch()
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", run)
    assert cli.main(["new", "../crm-api", "--preset", "crm", "--dry-run"]) == 0
    command, kwargs = calls[0]
    assert command[:2] == [cli.sys.executable, str(script)]
    assert command[2:5] == ["../crm-api", "--name", "crm-api"]
    assert command[-1] == "--dry-run"
    assert kwargs["cwd"] == tmp_path


def test_cli_add_and_upgrade_use_trusted_source_and_no_shell(tmp_path, monkeypatch):
    project, _ = _workspace(tmp_path)
    source = tmp_path / "source"
    (source / "apps").mkdir(parents=True)
    (source / "scripts").mkdir()
    (source / "scripts" / "module_upgrade.py").touch()
    (project / "primarykit-origin.json").write_text("{}", encoding="utf-8")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", run)
    assert (
        cli.main(
            ["add", "listings", "--project", str(project), "--source", str(source), "--dry-run"]
        )
        == 0
    )
    assert calls[0][0][1:4] == ["manage.py", "install_kit_module", "listings"]
    assert calls[0][0][-1] == "--dry-run"
    assert calls[0][1] == {"cwd": project, "check": False}
    assert (
        cli.main(["upgrade", "--project", str(project), "--source", str(source), "--dry-run"]) == 0
    )
    assert calls[1][0][1] == str(source / "scripts" / "module_upgrade.py")
    assert "--apply-safe" not in calls[1][0]
    assert "--apply-three-way" not in calls[1][0]


def test_cli_rejects_self_module_copy(tmp_path):
    project, _ = _workspace(tmp_path)
    (project / "apps").mkdir()
    assert cli.main(["add", "orders", "--project", str(project), "--source", str(project)]) == 1


def test_typescript_sdk_dry_run_is_offline_and_read_only(tmp_path, capsys):
    project, frontend = _workspace(tmp_path)
    assert (
        typescript_sdk.generate_typescript_sdk(
            project=project, frontend=frontend, output=Path("src/api"), dry_run=True
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["schema_source"] == "manage.py spectacular"
    assert not (frontend / "src").exists()


def test_typescript_sdk_rejects_traversal_and_existing_client(tmp_path):
    project, frontend = _workspace(tmp_path)
    with pytest.raises(ValueError, match="inside"):
        typescript_sdk.generate_typescript_sdk(
            project=project, frontend=frontend, output=Path("../escaped"), dry_run=True
        )
    dest = frontend / "src" / "api"
    dest.mkdir(parents=True)
    (dest / "client.ts").write_text("handwritten", encoding="utf-8")
    with pytest.raises(ValueError, match="--force"):
        typescript_sdk.generate_typescript_sdk(
            project=project, frontend=frontend, output=Path("src/api"), dry_run=True
        )
    assert (dest / "client.ts").read_text() == "handwritten"


def test_typescript_sdk_never_fetches_schema_from_url(tmp_path):
    project, frontend = _workspace(tmp_path)
    with pytest.raises(ValueError, match="local YAML"):
        typescript_sdk.generate_typescript_sdk(
            project=project,
            frontend=frontend,
            output=Path("src/api"),
            schema=Path("https://example.com/schema.yaml"),
            dry_run=True,
        )


def test_typescript_sdk_stages_then_publishes(tmp_path, monkeypatch):
    project, frontend = _workspace(tmp_path)
    binary = frontend / "node_modules" / ".bin" / "openapi-typescript"
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.setattr(typescript_sdk.os, "name", "posix")
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        if "spectacular" in command:
            path = Path(command[command.index("--file") + 1])
            path.write_text("openapi: 3.0.3\npaths: {}\n", encoding="utf-8")
        else:
            assert command[0] == str(binary)
            Path(command[-1]).write_text("export interface paths {}\n", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(typescript_sdk.subprocess, "run", run)
    assert (
        typescript_sdk.generate_typescript_sdk(
            project=project, frontend=frontend, output=Path("src/api")
        )
        == 0
    )
    output = frontend / "src" / "api"
    assert (output / "schema.d.ts").read_text() == "export interface paths {}\n"
    assert "createPrimaryKitClient" in (output / "client.ts").read_text()
    assert len(commands) == 2
    assert all(kwargs["check"] is True for _, kwargs in commands)


def test_typescript_sdk_failed_generator_preserves_frontend(tmp_path, monkeypatch):
    project, frontend = _workspace(tmp_path)
    binary = frontend / "node_modules" / ".bin" / "openapi-typescript"
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.setattr(typescript_sdk.os, "name", "posix")
    out = frontend / "src" / "api"
    out.mkdir(parents=True)
    (out / "client.ts").write_text("existing", encoding="utf-8")
    (out / "schema.d.ts").write_text("old", encoding="utf-8")
    schema = project / "openapi.yaml"
    schema.write_text("openapi: 3.0.3\npaths: {}\n", encoding="utf-8")

    def fail(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(typescript_sdk.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        typescript_sdk.generate_typescript_sdk(
            project=project,
            frontend=frontend,
            output=Path("src/api"),
            schema=Path("openapi.yaml"),
            force=True,
        )
    assert (out / "client.ts").read_text() == "existing"
    assert (out / "schema.d.ts").read_text() == "old"
