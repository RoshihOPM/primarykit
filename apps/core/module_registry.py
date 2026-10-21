"""Discover portable Django modules by their colocated manifest.py files.

Copying a module directory under apps/ is enough to register it if its declared
hard dependencies are present. Never silently enable missing dependencies.
"""

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path


class ModuleConfigurationError(ValueError):
    """Malformed module definition or missing/cyclic required dependencies."""


@dataclass(frozen=True)
class Route:
    prefix: str
    requires: tuple[str, ...] = ()
    mode: str | None = None
    urlconf: str | None = None


@dataclass(frozen=True)
class Module:
    name: str
    requires: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    routes: tuple[Route, ...] = ()
    priority: int = 100
    migration_policy: str = "none"  # none or client (client-owned migrations)


def discover_modules(root: Path | None = None) -> dict[str, Module]:
    """Load source-controlled manifests; do not execute arbitrary downloaded code."""
    root = root or Path(__file__).resolve().parents[1]
    found = {}
    for directory in sorted(root.iterdir()):
        if not directory.is_dir() or not (directory / "__init__.py").is_file():
            continue
        if not (directory / "manifest.py").is_file():
            continue
        name = directory.name
        if not name.isidentifier() or not (directory / "apps.py").is_file():
            raise ModuleConfigurationError(f"Invalid Django module directory: {directory}")
        manifest = import_module(f"apps.{name}.manifest")
        module = getattr(manifest, "MODULE", None)
        if not isinstance(module, Module) or module.name != name:
            raise ModuleConfigurationError(f"Invalid manifest in apps.{name}")
        found[name] = module
    return found


def resolve_modules(modules: dict[str, Module]) -> tuple[Module, ...]:
    """Topological order with explicit cycle and missing-dependency failures."""
    ordered = []
    visiting = set()
    visited = set()

    def visit(name: str):
        if name in visited:
            return
        if name in visiting:
            raise ModuleConfigurationError(f"Cyclic module dependency: {name}")
        if name not in modules:
            raise ModuleConfigurationError(
                f"Required module '{name}' is missing. Copy apps/{name}/ "
                "or install its dependency bundle before starting Django."
            )
        visiting.add(name)
        module = modules[name]
        for dependency in module.requires:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        ordered.append(module)

    for name in sorted(modules, key=lambda n: (modules[n].priority, n)):
        visit(name)
    return tuple(ordered)


def active_modules() -> tuple[Module, ...]:
    return resolve_modules(discover_modules())


def installed_module_apps() -> list[str]:
    return [f"apps.{module.name}" for module in active_modules()]


def module_routes() -> tuple[tuple[str, str], ...]:
    """Registered endpoints including only available optional integrations."""
    from django.conf import settings

    modules = active_modules()
    installed = {module.name for module in modules}
    result = []
    for module in sorted(modules, key=lambda item: (item.priority, item.name)):
        mode = getattr(settings, f"{module.name.upper()}_MODE", None)
        if module.name in {"catalog", "inventory"} and mode == "tenant":
            required = {"organizations"} | ({"catalog"} if module.name == "inventory" else set())
            if not required.issubset(installed):
                raise ModuleConfigurationError(
                    f"{module.name} tenant mode requires: {sorted(required)}"
                )
        for route in module.routes:
            if route.mode is not None and route.mode != mode:
                continue
            if all(dependency in installed for dependency in route.requires):
                result.append((route.prefix, route.urlconf or f"apps.{module.name}.urls"))
    return tuple(result)


def dependency_closure(modules: dict[str, Module], selected: set[str]) -> set[str]:
    """Resolve required module files for the project generator and copy installer."""
    missing = selected - modules.keys()
    if missing:
        raise ModuleConfigurationError(f"Unknown modules: {', '.join(sorted(missing))}")
    result = set()

    def add(name, chain=()):
        if name in chain:
            raise ModuleConfigurationError(
                f"Cyclic module dependency: {' -> '.join((*chain, name))}"
            )
        if name in result:
            return
        module = modules.get(name)
        if module is None:
            raise ModuleConfigurationError(f"Required module '{name}' is missing")
        for dep in module.requires:
            add(dep, (*chain, name))
        result.add(name)

    for name in sorted(selected):
        add(name)
    return result


def migration_apps(modules: dict[str, Module] | None = None) -> tuple[str, ...]:
    """Return app labels requiring client-owned Django migrations."""
    ordered = resolve_modules(modules if modules is not None else discover_modules())
    for module in ordered:
        if module.migration_policy not in {"none", "client"}:
            raise ModuleConfigurationError(
                f"Invalid migration policy in {module.name}: {module.migration_policy}"
            )
    return tuple(module.name for module in ordered if module.migration_policy == "client")
