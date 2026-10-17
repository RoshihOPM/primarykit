import json
import tomllib

import pytest

from apps.core.module_registry import dependency_closure, discover_modules
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
        {"observability"},
        {"feature_flags"},
        {"search"},
        {"csv_exchange"},
        {"api_keys"},
        {"idempotency"},
        {"outbox"},
        {"webhooks"},
        {"cache"},
        {"rate_limit"},
        {"celery_tasks"},
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
        "observability",
        "feature_flags",
        "search",
        "csv_exchange",
        "api_keys",
        "idempotency",
        "outbox",
        "webhooks",
        "cache",
        "rate_limit",
        "celery_tasks",
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
    migration_apps = (
        "users"
        + (" audit" if "audit" in apps else "")
        + (" storage" if "storage" in apps else "")
        + (" catalog" if "catalog" in selected else "")
        + (" inventory" if "inventory" in selected else "")
        + (" organizations" if "organizations" in selected else "")
        + (" orders" if "orders" in selected else "")
        + (" sales" if "sales" in selected else "")
        + (" payments" if "payments" in selected else "")
        + (" tasks" if "tasks" in selected else "")
        + (" webhooks" if "webhooks" in selected else "")
        + (" api_keys" if "api_keys" in selected else "")
        + (" idempotency" if "idempotency" in selected else "")
    )
    assert workflows.count(f"makemigrations {migration_apps} --noinput") == 2
    if "storage" in selected:
        assert (target / "apps/storage/tests/test_personal_storage.py").exists()
        assert (target / "apps/storage/tests/test_storage.py").exists()


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
