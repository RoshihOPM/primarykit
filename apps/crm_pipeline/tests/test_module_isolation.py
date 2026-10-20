"""Standalone module boundaries are never replaced by an implicit CRM dependency."""

from apps.core.module_registry import dependency_closure, discover_modules


def test_pipeline_adapter_is_an_explicit_dependency_bundle():
    modules = discover_modules()
    assert set(modules["crm_pipeline"].requires) == {"deals", "kanban"}
    assert "crm_pipeline" not in dependency_closure(modules, {"deals"})
    assert "crm_pipeline" not in dependency_closure(modules, {"kanban"})
    assert {"deals", "kanban", "users"} <= dependency_closure(
        modules, {"crm_pipeline"}
    )
