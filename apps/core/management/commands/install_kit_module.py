"""Install a portable module and its hard dependencies from a trusted source kit.

Usage in a generated project:
    python manage.py install_kit_module storage --source ../primarykit
    python manage.py install_kit_module inventory --source ../primarykit
Restart Django and generate/commit migrations afterwards.
"""

import ast
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

MODULE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _declared_dependencies(source: Path, name: str) -> tuple[str, ...]:
    """Read only literal metadata, never import/execute code from source kit."""
    if not MODULE_NAME.fullmatch(name):
        raise CommandError("Invalid module name.")
    directory = source / "apps" / name
    path = directory / "manifest.py"
    if not path.is_file() or not (directory / "apps.py").is_file():
        raise CommandError(f"Missing installable module apps/{name} in {source}")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        definitions = [
            stmt.value
            for stmt in tree.body
            if isinstance(stmt, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "MODULE" for target in stmt.targets
            )
        ]
        if len(definitions) != 1 or not isinstance(definitions[0], ast.Call):
            raise ValueError("Expected one Module() declaration")
        values = {kw.arg: kw.value for kw in definitions[0].keywords}
        if ast.literal_eval(values["name"]) != name:
            raise ValueError("Manifest name mismatch")
        requires = ast.literal_eval(values.get("requires", ast.Tuple(elts=[], ctx=ast.Load())))
        if not isinstance(requires, tuple) or not all(
            isinstance(dep, str) and MODULE_NAME.fullmatch(dep) for dep in requires
        ):
            raise ValueError("Dependencies must be a tuple of module names")
        return requires
    except (SyntaxError, ValueError, KeyError, TypeError) as exc:
        raise CommandError(f"Invalid module manifest: {path}") from exc


def install_order(*, source: Path, existing: set[str], requested: str) -> list[str]:
    ordered: list[str] = []
    visiting: set[str] = set()
    processed: set[str] = set()

    def visit(name: str):
        if name in processed:
            return
        if name in visiting:
            raise CommandError(f"Cyclic dependency at {name}")
        visiting.add(name)
        for dependency in _declared_dependencies(source, name):
            visit(dependency)
        visiting.remove(name)
        processed.add(name)
        if name not in existing:
            ordered.append(name)

    visit(requested)
    return ordered



def _module_fingerprint(folder: Path) -> dict[str, str]:
    """Snapshot copied runtime Python files, matching the project generator."""
    return {
        path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*.py"))
        if not {"migrations", "tests", "__pycache__"} & set(path.parts)
    }


def _updated_origin(origin: Path, order: list[str], stage: Path) -> str | None:
    """Prepare provenance before moving any module into the running project."""
    if not origin.is_file():
        return None  # Provenance is optional for existing client projects.
    try:
        data = json.loads(origin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CommandError("Cannot read client provenance; no modules installed.") from exc
    if not isinstance(data, dict):
        raise CommandError("Invalid client provenance object; no modules installed.")
    included = data.get("included_apps")
    fingerprints = data.get("module_fingerprints")
    if (
        not isinstance(included, list)
        or not all(isinstance(name, str) for name in included)
        or not isinstance(fingerprints, dict)
    ):
        raise CommandError("Invalid client provenance metadata; no modules installed.")
    if set(order) & (set(included) | set(fingerprints)):
        raise CommandError("Client provenance already names a module missing on disk.")

    for name in order:
        fingerprints[name] = _module_fingerprint(stage / name)
    data["included_apps"] = sorted(set(included) | set(order))
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


class Command(BaseCommand):
    help = "Copy a selected PrimaryKit module and all required module folders."

    def add_arguments(self, parser):
        parser.add_argument("module")
        parser.add_argument(
            "--source", required=True, type=Path, help="Trusted PrimaryKit checkout"
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        source = options["source"].expanduser().resolve()
        destination = Path(settings.BASE_DIR).resolve()
        if source == destination:
            raise CommandError("Use a separate PrimaryKit checkout as source.")
        if not (source / "apps").is_dir() or not (destination / "apps").is_dir():
            raise CommandError("Expected apps/ in both source and destination.")
        existing = {path.name for path in (destination / "apps").iterdir() if path.is_dir()}
        order = install_order(source=source, existing=existing, requested=options["module"])
        if not order:
            self.stdout.write("Module and all dependencies are already present.")
            return
        self.stdout.write("Will install: " + ", ".join(order))
        if options["dry_run"]:
            return

        # Copy outside active module paths first. On failure, remove new folders.
        created = []
        try:
            with TemporaryDirectory(prefix=".primarykit-install-", dir=destination) as temp:
                stage = Path(temp)
                for name in order:
                    shutil.copytree(
                        source / "apps" / name,
                        stage / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
                        symlinks=False,
                    )
                final = existing | set(order)
                if "storage" in order and "organizations" not in final:
                    # Tenant test modules require optional Organizations models.
                    for name in ("test_storage.py", "test_seaweedfs_integration.py"):
                        (stage / "storage" / "tests" / name).unlink(missing_ok=True)
                origin = destination / "primarykit-origin.json"
                updated = _updated_origin(origin, order, stage)
                if updated is not None:
                    staged_origin = stage / "primarykit-origin.json"
                    staged_origin.write_text(updated, encoding="utf-8")
                for name in order:
                    target = destination / "apps" / name
                    if target.exists():
                        raise CommandError(f"Module already exists: {target}")
                    (stage / name).rename(target)
                    created.append(target)
                # Single atomic metadata replacement, after all folders are installed.
                # If this fails, the original JSON remains intact and folders roll back.
                if updated is not None:
                    os.replace(staged_origin, origin)
        except (OSError, ValueError, CommandError) as exc:
            for path in reversed(created):
                shutil.rmtree(path, ignore_errors=True)
            raise CommandError(f"Module installation failed: {exc}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Installed. Restart Django; run makemigrations for the new apps and migrate. "
                "Commit generated migrations in your project."
            )
        )
