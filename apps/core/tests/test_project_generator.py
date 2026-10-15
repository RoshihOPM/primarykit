import json

import pytest

from scripts.new_project import create_project


@pytest.mark.parametrize(
    "apps",
    [
        set(),
        {"audit"},
        {"storage"},
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
    selected = apps | ({"catalog"} if "inventory" in apps else set())
    for app in ("rbac", "audit", "storage", "catalog", "inventory", "organizations"):
        assert (target / "apps" / app).exists() == (app in selected)

    settings = (target / "config/settings/base.py").read_text()
    urls = (target / "config/urls.py").read_text()
    for app, prefix in (
        ("rbac", "api/v1/admin/rbac/"),
        ("audit", "api/v1/admin/audit/"),
        ("storage", 'include("apps.storage.urls")'),
        ("catalog", 'include("apps.catalog.urls")'),
        ("inventory", 'include("apps.inventory.urls")'),
        ("organizations", 'include("apps.organizations.urls")'),
    ):
        assert (f'"apps.{app}"' in settings) == (app in selected)
        assert (prefix in urls) == (app in selected)

    assert 'name = "demo-api"' in (target / "pyproject.toml").read_text()
    assert 'name = "demo-api"' in (target / "uv.lock").read_text()
    assert not (target / "scripts").exists()
    assert not (target / "apps/core/tests/test_project_generator.py").exists()
    assert not (target / ".git").exists()
    assert not (target / ".env").exists()
    assert (target / ".env.example").exists()
    assert (target / "compose.seaweedfs.yaml").exists() == ("storage" in apps)

    metadata = json.loads((target / "primarykit-origin.json").read_text())
    assert set(metadata["included_apps"]) == {"core", "users", "notifications"} | selected
    workflows = (target / ".github/workflows/ci.yaml").read_text()
    migration_apps = (
        "users"
        + (" audit" if "audit" in apps else "")
        + (" storage" if "storage" in apps else "")
        + (" catalog" if "catalog" in selected else "")
        + (" inventory" if "inventory" in selected else "")
        + (" organizations" if "organizations" in selected else "")
    )
    assert workflows.count(f"makemigrations {migration_apps} --noinput") == 2


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
