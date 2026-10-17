#!/usr/bin/env python3
"""Source-catalog-only scaffolding and static dependency graph for Django modules.

This tool must not be copied into generated client backends. It neither imports
module manifests nor provisions dependencies, databases or migrations.
"""

import argparse
import ast
import json
import keyword
import re
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")


def validate_name(name: str) -> str:
    if not MODULE_NAME.fullmatch(name) or keyword.iskeyword(name):
        raise ValueError("Module names must be lowercase Python identifiers, not keywords")
    return name


def _source_apps(root: Path) -> Path:
    """Refuse to operate on a generated client or arbitrary directory."""
    apps = root / "apps"
    if not (apps / "__init__.py").is_file() or not (root / "scripts/new_project.py").is_file():
        raise ValueError(
            "Expected a PrimaryKit source checkout with apps/ and scripts/new_project.py"
        )
    return apps


def _metadata(path: Path, name: str) -> dict:
    """Read literal manifest metadata using AST without executing module code."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    declarations = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "MODULE" for t in node.targets)
    ]
    if len(declarations) != 1 or not isinstance(declarations[0], ast.Call):
        raise ValueError(f"Invalid MODULE declaration: {path}")
    call = declarations[0]
    if not (
        isinstance(call.func, ast.Name)
        and call.func.id == "Module"
        or isinstance(call.func, ast.Attribute)
        and call.func.attr == "Module"
    ):
        raise ValueError(f"Invalid Module constructor: {path}")
    if call.args or any(kw.arg is None for kw in call.keywords):
        raise ValueError(f"Unsupported manifest syntax: {path}")
    kwargs = {kw.arg: kw.value for kw in call.keywords}
    if len(kwargs) != len(call.keywords) or ast.literal_eval(kwargs["name"]) != name:
        raise ValueError(f"Manifest name mismatch: {path}")
    result = {"name": name}
    for field in ("requires", "optional"):
        value = ast.literal_eval(kwargs[field]) if field in kwargs else ()
        if not isinstance(value, tuple) or any(
            not isinstance(item, str) or not MODULE_NAME.fullmatch(item) or keyword.iskeyword(item)
            for item in value
        ):
            raise ValueError(f"Invalid {field} declaration: {path}")
        if len(value) != len(set(value)):
            raise ValueError(f"Duplicate {field} declaration: {path}")
        result[field] = list(value)
    return result


def dependency_graph(root: Path = SOURCE_ROOT) -> dict:
    """Enumerate source manifest dependencies without Django setup or imports."""
    apps = _source_apps(root)
    modules = []
    for folder in sorted(apps.iterdir()):
        manifest = folder / "manifest.py"
        if folder.is_dir() and manifest.is_file():
            validate_name(folder.name)
            modules.append(_metadata(manifest, folder.name))
    names = {module["name"] for module in modules}
    for module in modules:
        missing = set(module["requires"]) - names
        if missing:
            raise ValueError(
                f"{module['name']} has missing dependencies: {', '.join(sorted(missing))}"
            )
    required = {module["name"]: module["requires"] for module in modules}
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(name: str):
        if name in visiting:
            raise ValueError(f"Cyclic required module dependencies involving {name}")
        if name in visited:
            return
        visiting.add(name)
        for dependency in required[name]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)

    for name in sorted(names):
        visit(name)
    return {"modules": modules}


def dependency_dot(graph: dict) -> str:
    """Render a deterministic Graphviz DOT graph; dashed links are optional."""
    modules = graph["modules"]
    names = {module["name"] for module in modules}
    lines = ["digraph primarykit_modules {", "  rankdir=LR;"]
    for name in sorted(names):
        lines.append(f'  "{name}";')
    for module in modules:
        name = module["name"]
        for dependency in sorted(module["requires"]):
            lines.append(f'  "{name}" -> "{dependency}" [style=solid];')
        for dependency in sorted(module["optional"]):
            if dependency in names:
                lines.append(f'  "{name}" -> "{dependency}" [style=dashed];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def scaffold_module(
    name: str,
    *,
    root: Path = SOURCE_ROOT,
    requires: tuple[str, ...] = (),
    dry_run: bool = False,
) -> dict:
    """Create a new module directory exclusively, or return a non-writing plan."""
    validate_name(name)
    if len(requires) != len(set(requires)):
        raise ValueError("Duplicate required dependencies")
    for dependency in requires:
        validate_name(dependency)
    graph = dependency_graph(root)
    existing = {module["name"] for module in graph["modules"]}
    missing = set(requires) - existing
    if missing:
        raise ValueError(f"Unknown required modules: {', '.join(sorted(missing))}")
    if name in requires:
        raise ValueError("A module cannot require itself")

    target = _source_apps(root) / name
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"Module directory already exists: {target}")
    class_name = "".join(part.capitalize() for part in name.split("_")) + "Config"
    files = {
        "__init__.py": "",
        "apps.py": (
            "from django.apps import AppConfig\n\n\n"
            f"class {class_name}(AppConfig):\n"
            '    default_auto_field = "django.db.models.BigAutoField"\n'
            f'    name = "apps.{name}"\n'
        ),
        "manifest.py": (
            '"""Portable module declaration. Add routes only when URLs exist."""\n\n'
            "from apps.core.module_registry import Module\n\n"
            f'MODULE = Module(name="{name}", requires={requires!r})\n'
        ),
        "tests/__init__.py": "",
        f"tests/test_{name}.py": (
            f"from apps.{name}.manifest import MODULE\n\n\n"
            f"def test_{name}_manifest():\n"
            f'    assert MODULE.name == "{name}"\n'
            f"    assert MODULE.requires == {requires!r}\n"
        ),
    }
    plan = {
        "module": name,
        "requires": list(requires),
        "dry_run": dry_run,
        "files": [f"apps/{name}/{path}" for path in sorted(files)],
    }
    if dry_run:
        return plan

    # mkdir without exist_ok is an atomic rejection of a pre-existing directory.
    target.mkdir(exist_ok=False)
    written = []
    subdirs = []
    try:
        for path, content in files.items():
            destination = target / path
            if destination.parent != target and not destination.parent.exists():
                destination.parent.mkdir()
                subdirs.append(destination.parent)
            with destination.open("x", encoding="utf-8", newline="\n") as output:
                output.write(content)
            written.append(destination)
    except Exception:
        # Clean up only our own paths, never delete arbitrary new files on failure.
        for path in reversed(written):
            path.unlink(missing_ok=True)
        for directory in reversed(subdirs):
            directory.rmdir()
        target.rmdir()
        raise
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Generate one safe source-catalog app")
    create.add_argument("name")
    create.add_argument("--requires", nargs="*", default=[], metavar="MODULE")
    create.add_argument("--dry-run", action="store_true")
    graph = commands.add_parser("graph", help="Print a static dependency graph")
    graph.add_argument("--format", choices=("json", "dot"), default="json")
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = scaffold_module(args.name, requires=tuple(args.requires), dry_run=args.dry_run)
            print(json.dumps(result, indent=2))
        else:
            result = dependency_graph()
            print(
                json.dumps(result, indent=2) if args.format == "json" else dependency_dot(result),
                end="\n" if args.format == "json" else "",
            )
    except (ValueError, FileExistsError, OSError, SyntaxError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
