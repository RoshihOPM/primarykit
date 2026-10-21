"""Offline checks for a copied Django project. No Django setup or PrimaryKit install required.

Run from the generated project's root:
    python -m apps.core.doctor
    python -m apps.core.doctor --json --strict
"""

import argparse
import ast
import json
import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

REQUIRED = frozenset({"core", "users", "notifications"})
MODULE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    detail: str


@dataclass(frozen=True)
class Report:
    modules: tuple[str, ...]
    findings: tuple[Finding, ...]

    def failed(self, *, strict: bool = False) -> bool:
        return any(
            item.level == "error" or (strict and item.level == "warning") for item in self.findings
        )


def _manifest(path: Path, name: str) -> tuple[str, ...]:
    """Inspect only literal manifest metadata. Never execute untrusted modules."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    declarations = [
        statement.value
        for statement in tree.body
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "MODULE" for target in statement.targets
        )
    ]
    if len(declarations) != 1 or not isinstance(declarations[0], ast.Call):
        raise ValueError("expected exactly one MODULE = Module(...) declaration")
    constructor = declarations[0].func
    if not (
        isinstance(constructor, ast.Name)
        and constructor.id == "Module"
        or isinstance(constructor, ast.Attribute)
        and constructor.attr == "Module"
    ):
        raise ValueError("MODULE must be created using Module(...)")
    kwargs = {argument.arg: argument.value for argument in declarations[0].keywords}
    if ast.literal_eval(kwargs["name"]) != name:
        raise ValueError("manifest module name does not match folder")
    requires = ast.literal_eval(kwargs.get("requires", ast.Tuple(elts=[], ctx=ast.Load())))
    if not isinstance(requires, tuple) or any(
        not isinstance(item, str) or not MODULE_NAME.fullmatch(item) for item in requires
    ):
        raise ValueError("requires must be a tuple of module names")
    # Validate typed manifest contributions statically. Doctor runs in copied
    # projects before Django imports, so never evaluate module Python code.
    known = {
        "name",
        "requires",
        "optional",
        "routes",
        "priority",
        "migration_policy",
        "env_settings",
        "middleware",
        "throttle_rates",
    }
    if set(kwargs) - known or any(key is None for key in kwargs):
        raise ValueError("unknown or unpacked manifest configuration field")
    for key in ("middleware", "throttle_rates"):
        if key not in kwargs:
            continue
        value = ast.literal_eval(kwargs[key])
        if not isinstance(value, tuple):
            raise ValueError(f"{key} must be a literal tuple")
        if key == "middleware":
            if any(
                not isinstance(item, str)
                or not item.startswith(f"apps.{name}.")
                or not re.fullmatch(r"[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)+", item)
                for item in value
            ) or len(set(value)) != len(value):
                raise ValueError("invalid or repeated module middleware")
        elif any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not re.fullmatch(r"[a-z][a-z0-9_]*", item[0])
            or not isinstance(item[1], str)
            or not item[1]
            for item in value
        ) or len({item[0] for item in value}) != len(value):
            raise ValueError("invalid or duplicate throttle configuration")
    declared: set[str] = set()
    if "env_settings" in kwargs:
        values = kwargs["env_settings"]
        if not isinstance(values, ast.Tuple):
            raise ValueError("env_settings must be a literal tuple")
        for item in values.elts:
            if not (
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == "EnvSetting"
                and len(item.args) == 3
                and not item.keywords
            ):
                raise ValueError("env_settings requires literal EnvSetting(name, kind, default)")
            field, kind, default = (ast.literal_eval(v) for v in item.args)
            if (
                not isinstance(field, str)
                or not re.fullmatch(r"[A-Z][A-Z0-9_]*", field)
                or not field.startswith(f"{name.upper()}_")
                or field in declared
                or kind not in {"bool", "int", "str", "list"}
                or not {
                    "bool": type(default) is bool,
                    "int": type(default) is int,
                    "str": isinstance(default, str),
                    "list": isinstance(default, tuple) and all(isinstance(v, str) for v in default),
                }[kind]
            ):
                raise ValueError("invalid or duplicate typed environment contribution")
            declared.add(field)
    if "migration_policy" in kwargs and ast.literal_eval(kwargs["migration_policy"]) not in {
        "none",
        "client",
        "bundled",
    }:
        raise ValueError("invalid migration policy")
    return requires


def _mode(path: Path, setting: str) -> str | None:
    if not path.is_file():
        return None
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assignments = [
        item.value
        for item in tree.body
        if isinstance(item, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == setting for target in item.targets)
    ]
    if len(assignments) != 1:
        return None
    try:
        value = ast.literal_eval(assignments[0])
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, str) else None


def _runtime_imports(root: Path):
    """Inspect application code only; tests and documentation may discuss the kit."""
    for directory in (root / "apps", root / "config"):
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.py")):
            if any(part in {"tests", "migrations", "__pycache__"} for part in path.parts):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeError):
                # Django / Ruff handles syntax errors; don't mislabel them as kit imports.
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = (alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = (node.module or "",)
                else:
                    continue
                if any(
                    name == "primarykit"
                    or name.startswith("primarykit.")
                    or name == "scripts.new_project"
                    or name.startswith("scripts.new_project.")
                    for name in names
                ):
                    yield path.relative_to(root).as_posix()


def inspect_project(root: Path) -> Report:
    root = root.resolve()
    findings: list[Finding] = []

    def add(level: str, code: str, detail: str):
        findings.append(Finding(level, code, detail))

    apps_dir = root / "apps"
    if not apps_dir.is_dir():
        return Report((), (Finding("error", "apps_missing", "Expected apps/ directory"),))

    dependencies: dict[str, tuple[str, ...]] = {}
    for folder in sorted(apps_dir.iterdir()):
        if not folder.is_dir() or not (folder / "manifest.py").is_file():
            continue
        name = folder.name
        if (
            not MODULE_NAME.fullmatch(name)
            or not (folder / "__init__.py").is_file()
            or not (folder / "apps.py").is_file()
        ):
            add("error", "module_structure", f"apps/{name}: missing Django module files")
            continue
        try:
            dependencies[name] = _manifest(folder / "manifest.py", name)
        except (OSError, ValueError, KeyError, SyntaxError, TypeError) as exc:
            add("error", "invalid_manifest", f"apps/{name}/manifest.py: {exc}")

    names = set(dependencies)
    for name in sorted(REQUIRED - names):
        add("error", "baseline_missing", f"Required baseline module apps/{name} is absent")

    for name, requires in sorted(dependencies.items()):
        for dependency in requires:
            if dependency not in names:
                add("error", "dependency_missing", f"{name} requires missing {dependency}")

    visiting: set[str] = set()
    done: set[str] = set()

    def visit(name: str):
        if name in done:
            return
        if name in visiting:
            add("error", "dependency_cycle", f"Cyclic dependency involving {name}")
            return
        visiting.add(name)
        for item in dependencies[name]:
            if item in dependencies:
                visit(item)
        visiting.remove(name)
        done.add(name)

    for name in sorted(names):
        visit(name)

    settings_path = root / "config" / "settings" / "base.py"
    if not settings_path.is_file():
        add("error", "settings_missing", "config/settings/base.py is missing")
    else:
        for module in ("catalog", "inventory"):
            if module not in names:
                continue
            mode = _mode(settings_path, f"{module.upper()}_MODE")
            if mode not in {"tenant", "standalone"}:
                add("warning", "schema_mode_unknown", f"{module}: check the pinned schema mode")
            elif mode == "tenant":
                needed = {"organizations"} | ({"catalog"} if module == "inventory" else set())
                if not needed <= names:
                    add(
                        "error",
                        "tenant_dependency_missing",
                        f"{module} tenant mode requires {', '.join(sorted(needed))}",
                    )

    project_name = None
    project_version = None
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        add("error", "pyproject_missing", "Missing pyproject.toml")
    else:
        try:
            project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
            project_name = project["name"]
            project_version = project["version"]
            for value in project.get("dependencies", ()):
                package = re.split(r"[\s\[<>=!~;]", value, maxsplit=1)[0]
                if package.lower().replace("_", "-") == "primarykit":
                    add("error", "kit_dependency", "Remove runtime PrimaryKit dependency")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            add("error", "invalid_pyproject", f"Invalid pyproject.toml: {exc}")

    # The copied uv.lock must describe THIS project's virtual root package.
    # A stale lock may pass static Django checks but fail uv sync --locked.
    lock_path = root / "uv.lock"
    if not lock_path.is_file():
        add("error", "lock_missing", "uv.lock is required for reproducible builds")
    else:
        try:
            lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
            virtual_roots = [
                package
                for package in lock.get("package", ())
                if package.get("source") == {"virtual": "."}
            ]
            if project_name is not None and (
                len(virtual_roots) != 1
                or virtual_roots[0].get("name") != project_name
                or virtual_roots[0].get("version") != project_version
            ):
                add(
                    "error",
                    "lock_root_mismatch",
                    "uv.lock virtual project name/version must match pyproject.toml",
                )
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            add("error", "invalid_lock", f"Invalid uv.lock: {exc}")

    for path in sorted(set(_runtime_imports(root))):
        add("error", "kit_import", f"Runtime import of source kit in {path}")

    # Optional provenance metadata is informational; it is not read by Django at runtime.
    metadata_path = root / "primarykit-origin.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            included = metadata.get("included_apps")
            if not isinstance(included, list) or not all(
                isinstance(value, str) for value in included
            ):
                add("warning", "origin_invalid", "Provenance included_apps is invalid")
            elif set(included) != names:
                add("warning", "origin_stale", "Optional provenance module list is outdated")
            modes = metadata.get("schema_modes", {})
            if not isinstance(modes, dict):
                add("error", "schema_modes_invalid", "Expected mapping of pinned schema modes")
            else:
                for module, original in modes.items():
                    if module not in {"catalog", "inventory"} or original not in {
                        "tenant",
                        "standalone",
                    }:
                        add("error", "schema_modes_invalid", f"Invalid pinned schema: {module}")
                    elif module in names:
                        actual = _mode(settings_path, f"{module.upper()}_MODE")
                        if actual != original:
                            add(
                                "error",
                                "schema_mode_changed",
                                f"{module} schema mode changed from {original!r} to {actual!r}; "
                                "do not switch an existing database without reviewed data migrations",
                            )
        except (OSError, ValueError, TypeError, AttributeError):
            add("warning", "origin_invalid", "Optional provenance JSON is unreadable")

    return Report(tuple(sorted(names)), tuple(findings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline copied-project health diagnostics")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project directory")
    parser.add_argument("--json", action="store_true", help="Machine-readable diagnostic report")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings as well as errors")
    args = parser.parse_args(argv)
    report = inspect_project(args.root)
    failed = report.failed(strict=args.strict)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": not failed,
                    "modules": list(report.modules),
                    "findings": [asdict(item) for item in report.findings],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"Modules: {', '.join(report.modules) or '(none)'}")
        for item in report.findings:
            print(f"{item.level.upper()} [{item.code}] {item.detail}")
        print("Project checks failed." if failed else "Project checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
