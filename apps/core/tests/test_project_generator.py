import json
import tomllib
from pathlib import Path

import pytest

from apps.core.module_registry import (
    dependency_closure,
    discover_modules,
    migration_apps,
)
from scripts.new_project import SOURCE_ROOT, create_project, project_plan
from scripts.presets import PRESETS


@pytest.mark.parametrize(
    "apps",
    [
        set(),
        {"audit"},
        {"storage"},
        {"orders"},
        {"sales"},
        {"payments"},
        {"tasks"},
        {"privacy"},
        {"listings"},
        {"favorites"},
        {"observability"},
        {"feature_flags"},
        {"search"},
        {"csv_exchange"},
        {"api_keys"},
        {"idempotency"},
        {"http_integrations"},
        {"outbox"},
        {"workflows"},
        {"webhooks"},
        {"cache"},
        {"rate_limit"},
        {"celery_tasks"},
        {"realtime"},
        {"chat"},
        {"chat", "realtime"},
        {"chat", "organizations", "storage", "realtime"},
        {"cache", "celery_tasks"},
        {"orders", "sales", "payments"},
        {"statistics", "orders", "sales", "payments"},
        {"statistics"},
        {"statistics", "catalog"},
        {"statistics", "inventory"},
        {"statistics", "organizations"},
        {"rbac"},
        {"catalog"},
        {"inventory"},
        {"organizations"},
        {"organizations", "audit"},
        {"inventory", "audit"},
        {"catalog", "storage"},
        {"audit", "storage", "rbac", "catalog", "inventory", "organizations"},
    ],
)
def test_project_generator_scopes_apps_and_urls(tmp_path, apps):
    target = create_project(tmp_path / "demo-api", name="demo-api", optional_apps=apps)
    assert target.is_dir()
    assert (target / "apps" / "core").exists()
    assert (target / "apps" / "users").exists()
    assert (target / "apps" / "notifications").exists()
    selected = dependency_closure(
        discover_modules(), {"core", "users", "notifications"} | set(apps)
    )
    for app in (
        "rbac",
        "audit",
        "storage",
        "catalog",
        "inventory",
        "organizations",
        "orders",
        "sales",
        "payments",
        "tasks",
        "privacy",
        "listings",
        "favorites",
        "observability",
        "feature_flags",
        "search",
        "csv_exchange",
        "api_keys",
        "idempotency",
        "http_integrations",
        "outbox",
        "workflows",
        "webhooks",
        "cache",
        "rate_limit",
        "celery_tasks",
        "chat",
        "realtime",
    ):
        assert (target / "apps" / app).exists() == (app in selected)

    settings = (target / "config/settings/base.py").read_text()
    urls = (target / "config/urls.py").read_text()
    assert ('CATALOG_MODE = "tenant"' in settings) == (
        "catalog" in selected and "organizations" in selected
    )
    assert ('INVENTORY_MODE = "tenant"' in settings) == (
        {"inventory", "catalog", "organizations"} <= selected
    )
    assert "*installed_module_apps()" in settings
    assert "module_routes()" in urls
    for name in selected:
        assert (target / "apps" / name / "manifest.py").is_file()
    for name in set(discover_modules()) - selected:
        assert not (target / "apps" / name).exists()

    assert 'name = "demo-api"' in (target / "pyproject.toml").read_text()
    assert 'name = "demo-api"' in (target / "uv.lock").read_text()
    assert '"TITLE": "demo-api API"' in settings
    assert not (target / "scripts").exists()
    assert not (target / "apps/core/tests/test_project_generator.py").exists()
    assert not (target / "apps/core/tests/test_doctor.py").exists()
    assert (target / "apps/core/doctor.py").is_file()
    assert not (target / ".git").exists()
    assert not (target / ".env").exists()
    assert (target / ".env.example").exists()
    assert (target / "compose.seaweedfs.yaml").exists() == ("storage" in apps)
    assert (target / "compose.redis.yaml").exists() == bool(
        {"cache", "celery_tasks", "rate_limit"} & apps
    )
    assert (target / "compose.celery.yaml").exists() == ("celery_tasks" in apps)
    assert (target / "compose.celery.prod.yaml").exists() == ("celery_tasks" in apps)
    if "cache" in apps:
        assert "REDIS_CACHE_KEY_PREFIX=demo-api-dev" in (target / ".env.example").read_text()
    readme = (target / "README.md").read_text()
    assert ("uv add 'redis>=8,<9'" in readme) == (
        "cache" in selected and "celery_tasks" not in selected
    )
    assert ("'redis>=6.2,<6.5'" in readme) == (
        {"cache", "celery_tasks"} <= apps or "celery_tasks" in apps
    )
    assert ("uv add 'celery>=5.6,<6'" in readme) == ("celery_tasks" in apps and "cache" not in apps)

    metadata = json.loads((target / "primarykit-origin.json").read_text())
    assert set(metadata["included_apps"]) == selected
    assert set(metadata["module_fingerprints"]) == selected
    for name in selected:
        assert metadata["module_fingerprints"][name]["manifest.py"]
    source_project = tomllib.loads((SOURCE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["source_version"] == source_project["project"]["version"]
    assert ("Feature flags: configure FEATURE_FLAGS" in readme) == ("feature_flags" in apps)
    workflows = (target / ".github/workflows/ci.yaml").read_text()
    assert "generated-clients:" not in workflows
    assert "scripts/lint_migration_sql.py" not in workflows
    assert "scripts/ci_generated_client.py" not in workflows
    assert project_plan(requested_apps=set(apps))["migrations"] == [
        name for name in migration_apps() if name in selected
    ]
    assert (
        workflows.count("makemigrations $(uv run python -m apps.core.migration_plan) --noinput")
        == 2
    )
    if "storage" in selected:
        assert (target / "apps/storage/tests/test_personal_storage.py").exists()
        assert (target / "apps/storage/tests/test_storage.py").exists()
    if "listings" in selected:
        assert 'STORAGES["listings_private"]' in settings
        assert (target / "apps/listings/tests/test_media.py").exists()
    if "chat" in selected:
        assert (target / "apps/chat/tests/test_chat.py").exists()
    if "realtime" in selected:
        assert (target / "apps/realtime/asgi.py").exists()
    if "favorites" in selected:
        assert (target / "apps/listings").is_dir()
        assert (target / "apps/favorites/tests/test_favorites.py").exists()


def test_generator_rejects_existing_directory_and_invalid_input(tmp_path):
    target = tmp_path / "backend"
    target.mkdir()
    with pytest.raises(FileExistsError):
        create_project(target, name="good-backend")
    with pytest.raises(ValueError):
        create_project(tmp_path / "not-created", name="../bad project")
    with pytest.raises(ValueError):
        create_project(tmp_path / "not-created", name="good-backend", optional_apps={"unknown"})


def test_generator_does_not_keep_secret_env_or_git_folders(tmp_path):
    dest = create_project(tmp_path / "client-backend", name="client-backend")
    assert not (dest / ".git").exists()
    assert not (dest / ".env").exists()
    assert not (dest / ".venv").exists()
    assert not (dest / "media").exists()
    assert not (dest / "privatefiles").exists()


@pytest.mark.parametrize("preset", sorted(PRESETS))
def test_generator_preset_portability_and_modes(tmp_path, preset):
    plan = project_plan(requested_apps=set(), preset=preset)
    assert set(plan["included_apps"]) >= {"core", "users", "notifications"}
    target = create_project(tmp_path / preset, name="preset-backend", preset=preset)
    metadata = json.loads((target / "primarykit-origin.json").read_text())
    assert metadata["preset"] == preset
    assert metadata["included_apps"] == plan["included_apps"]
    for name in set(discover_modules()) - set(plan["included_apps"]):
        assert not (target / "apps" / name).exists()


def test_dry_run_and_presets_do_not_write_files(tmp_path, capsys, monkeypatch):
    from scripts.new_project import main

    target = tmp_path / "does-not-exist"
    monkeypatch.setattr(
        "sys.argv",
        ["new_project.py", str(target), "--name", "dry-api", "--preset", "crm", "--dry-run"],
    )
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["preset"] == "crm"
    assert "organizations" in result["included_apps"]
    assert not target.exists()


def test_generated_client_keeps_license_not_upstream_governance(tmp_path):
    target = create_project(tmp_path / "client-api", name="client-api")
    source_license = (SOURCE_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert source_license.startswith("MIT License")
    assert (target / "LICENSE").read_text(encoding="utf-8") == source_license
    assert "preserve the included LICENSE" in (target / "README.md").read_text(encoding="utf-8")
    for source_only in (
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        ".github/CODEOWNERS",
        ".github/dependabot.yml",
        ".github/workflows/quality-tools.yml",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE",
        "docs/maintainer-playbook.md",
        "CHANGELOG.md",
    ):
        assert not (target / source_only).exists(), source_only


def test_bundled_migration_folders_preserved_only_when_declared(monkeypatch):
    from apps.core.module_registry import Module
    from scripts import new_project

    monkeypatch.setitem(
        new_project.AVAILABLE_MODULES,
        "fake_versioned",
        Module("fake_versioned", migration_policy="bundled"),
    )
    assert "migrations" not in new_project._ignore_excluded(
        "/root/apps/fake_versioned", ["migrations"]
    )
    assert "migrations" in new_project._ignore_excluded(
        "/root/apps/fake_unversioned", ["migrations"]
    )


def test_generator_racing_creator_does_not_delete_unowned_destination(tmp_path, monkeypatch):
    """The destination must be claimed exclusively before cleanup is allowed."""
    destination = tmp_path / "raced-backend"
    original_mkdir = Path.mkdir

    def competing_creator(path, *args, **kwargs):
        if path == destination:
            original_mkdir(path, *args, **kwargs)
            (path / "belongs-to-other-process.txt").write_text("keep me", encoding="utf-8")
            raise FileExistsError("another process claimed the destination")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", competing_creator)
    with pytest.raises(FileExistsError, match="another process"):
        create_project(destination, name="raced-backend")

    assert (destination / "belongs-to-other-process.txt").read_text(encoding="utf-8") == "keep me"


def test_generator_failed_copy_removes_only_claimed_destination(tmp_path, monkeypatch):
    from scripts import new_project

    destination = tmp_path / "failed-backend"
    neighbor = tmp_path / "existing-neighbor"
    neighbor.mkdir()
    (neighbor / "keep.txt").write_text("keep me", encoding="utf-8")

    def fail_partway(_source, target, **kwargs):
        assert kwargs["dirs_exist_ok"] is True
        assert target.is_dir()
        (target / "partial.txt").write_text("incomplete", encoding="utf-8")
        raise OSError("simulated partial copy failure")

    monkeypatch.setattr(new_project.shutil, "copytree", fail_partway)
    with pytest.raises(OSError, match="partial copy"):
        create_project(destination, name="failed-backend")

    assert not destination.exists()
    assert (neighbor / "keep.txt").read_text(encoding="utf-8") == "keep me"


def test_generated_project_includes_ub_mode(tmp_path):
    target = create_project(tmp_path / "client-api", name="client-api")
    skill = target / ".agents" / "skills" / "ub-mode" / "SKILL.md"
    assert skill.is_file()
    assert "original PrimaryKit adaptation" in skill.read_text(encoding="utf-8")
    assert ".agents/skills/ub-mode/SKILL.md" in (target / "AGENTS.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("ignored_name", [".quality-tools", ".metrics", "target"])
def test_generated_client_excludes_optional_quality_artifacts(tmp_path, ignored_name):
    from scripts import new_project

    assert ignored_name in new_project._ignore_excluded("/path/to/source", [ignored_name])
    project = create_project(tmp_path / "client", name="client-api")
    assert not (project / ignored_name).exists()
