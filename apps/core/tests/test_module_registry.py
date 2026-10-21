"""Regression tests for copy-by-directory discovery and dependency resolution."""

from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.core.management.commands.install_kit_module import install_order
from apps.core.module_registry import (
    EnvSetting,
    Module,
    ModuleConfigurationError,
    Route,
    active_modules,
    dependency_closure,
    discover_modules,
    migration_apps,
    module_env_settings,
    module_middleware,
    module_routes,
    module_throttle_rates,
    resolve_modules,
)


def test_source_manifests_are_discovered_and_topologically_ordered():
    found = discover_modules()
    ordered = active_modules()
    names = [entry.name for entry in ordered]
    assert names.index("core") < names.index("users")
    assert names.index("notifications") < names.index("users")
    assert {"core", "users", "notifications"}.issubset(found)
    for name, definition in found.items():
        for dependency in definition.requires:
            assert names.index(dependency) < names.index(name)


def test_optional_scoped_routes_are_registered_only_when_dependency_exists():
    installed = set(discover_modules())
    routes = set(module_routes())
    if "storage" in installed:
        assert ("api/v1/", "apps.storage.urls") in routes
        assert (("api/v1/organizations/<uuid:org_id>/", "apps.storage.urls") in routes) == (
            "organizations" in installed
        )
    if "inventory" in installed:
        prefix = (
            "api/v1/organizations/<uuid:org_id>/inventory/"
            if settings.INVENTORY_MODE == "tenant"
            else "api/v1/inventory/"
        )
        assert (prefix, "apps.inventory.urls") in routes


def test_registry_denies_missing_and_cyclic_modules():
    valid = {"core": Module("core"), "addon": Module("addon", requires=("core",))}
    assert [m.name for m in resolve_modules(valid)] == ["core", "addon"]
    assert dependency_closure(valid, {"addon"}) == {"core", "addon"}
    with pytest.raises(ModuleConfigurationError, match="missing"):
        resolve_modules({"inventory": Module("inventory", requires=("catalog",))})
    with pytest.raises(ModuleConfigurationError, match="Cyclic"):
        resolve_modules({"a": Module("a", requires=("b",)), "b": Module("b", requires=("a",))})
    with pytest.raises(ModuleConfigurationError, match="Unknown"):
        dependency_closure(valid, {"unknown"})


def test_route_manifest_remains_data_only():
    assert Route("api/v1/", requires=("organizations",)).requires == ("organizations",)


def _fake_module(source: Path, name: str, requires=()):
    folder = source / "apps" / name
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text("")
    (folder / "apps.py").write_text("# portable module\n")
    (folder / "manifest.py").write_text(
        f"from apps.core.module_registry import Module\n"
        f'MODULE = Module(name="{name}", requires={requires!r})\n'
    )


def test_copy_installer_recursively_installs_required_dependencies(tmp_path):
    source = tmp_path / "kit"
    destination = tmp_path / "client"
    (destination / "apps").mkdir(parents=True)
    for name in ("core", "users", "notifications"):
        _fake_module(source, name)
        (destination / "apps" / name).mkdir()
    _fake_module(source, "organizations", requires=("users",))
    _fake_module(source, "catalog", requires=("organizations",))
    _fake_module(source, "inventory", requires=("catalog", "organizations"))
    assert install_order(
        source=source, existing={"core", "users", "notifications"}, requested="inventory"
    ) == ["organizations", "catalog", "inventory"]
    with override_settings(BASE_DIR=destination):
        call_command("install_kit_module", "inventory", source=source, verbosity=0)
    assert (destination / "apps" / "inventory" / "manifest.py").exists()
    assert (destination / "apps" / "catalog" / "manifest.py").exists()
    assert (destination / "apps" / "organizations" / "manifest.py").exists()
    assert (destination / "apps" / "users").exists()


def test_copy_installer_does_not_write_on_invalid_dependency(tmp_path):
    source = tmp_path / "kit"
    destination = tmp_path / "client"
    (destination / "apps").mkdir(parents=True)
    _fake_module(source, "broken", requires=("absent",))
    with override_settings(BASE_DIR=destination):
        with pytest.raises(CommandError, match="Missing installable module"):
            call_command("install_kit_module", "broken", source=source)
    assert not (destination / "apps" / "broken").exists()


def test_manifest_migration_policies_match_schema_owners():
    found = discover_modules()
    labels = set(migration_apps(found))
    assert "users" in labels
    assert {"tasks", "orders", "api_keys", "webhooks"} & set(found) <= labels
    assert {"core", "notifications", "statistics", "observability"}.isdisjoint(labels)
    with pytest.raises(ModuleConfigurationError, match="Invalid migration policy"):
        migration_apps({"bad": Module("bad", migration_policy="invalid")})


def test_manifest_configuration_contributions_are_typed_and_scoped():
    import environ

    entries = {
        "chat": Module(
            "chat",
            env_settings=(EnvSetting("CHAT_RETENTION_DAYS", "int", 30),),
            middleware=("apps.chat.middleware.request_tracking",),
            throttle_rates=(("chat_read", "120/min"),),
        )
    }
    result = module_env_settings(environ.Env(), entries)
    assert result["CHAT_RETENTION_DAYS"] == 30
    assert module_middleware(entries) == ("apps.chat.middleware.request_tracking",)
    assert module_throttle_rates(entries) == {"chat_read": "120/min"}


@pytest.mark.parametrize(
    "definition",
    [
        Module("a", env_settings=(EnvSetting("DJANGO_SECRET_KEY", "str", "bad"),)),
        Module("a", env_settings=(EnvSetting("A_PORT", "int", "bad"),)),
        Module("a", middleware=("apps.other.middleware.unsafe",)),
        Module("a", throttle_rates=(("bad key", "10/min"),)),
    ],
)
def test_manifest_configuration_rejects_invalid_declarations(definition):
    with pytest.raises(ModuleConfigurationError):
        module_middleware({"a": definition})
