from apps.core.module_registry import dependency_closure, discover_modules


def test_leads_and_kanban_are_not_hard_or_optional_coupled():
    modules = discover_modules()
    assert "kanban" not in modules["leads"].requires
    assert "kanban" not in modules["leads"].optional
    assert "leads" not in modules["kanban"].requires
    assert "leads" not in modules["kanban"].optional
    assert "kanban" not in dependency_closure(modules, {"leads"})
    assert "leads" not in dependency_closure(modules, {"kanban"})
