"""Install a portable module and its hard dependencies from a trusted source kit.

Usage in a generated project:
    python manage.py install_kit_module storage --source ../primarykit
    python manage.py install_kit_module inventory --source ../primarykit
Restart Django afterwards. Generate and commit migrations for modules whose
manifest declares ``migration_policy="client"``; ``bundled`` modules ship theirs.

Self-contained on purpose: this file is copied into clients, so it never imports
``scripts.*`` or any Python from the source checkout. Manifests are read statically.
"""

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.doctor import _manifest as _validate_manifest

MODULE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
NEVER_COPIED = ("__pycache__", "*.pyc", ".pytest_cache")


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


def _copy_ignore(module: Path, policy: str):
    """Skip caches and, unless the history is bundled, the module's migrations."""
    caches = shutil.ignore_patterns(*NEVER_COPIED)

    def ignore(directory, names):
        ignored = set(caches(directory, names))
        if policy != "bundled" and Path(directory) == module:
            ignored.add("migrations")
        return ignored

    return ignore


def _inspect_modules(apps: Path, order: list[str]) -> dict[str, str]:
    """Check module trees under ``apps`` and return each migration policy.

    Runs on the source before anything is written and again on the staged copy,
    so the bytes that get installed are the bytes that were validated. Manifests
    are parsed by this project's own static validator and never executed.
    """
    policies = {}
    for name in order:
        module = apps / name
        manifest = module / "manifest.py"
        if module.is_symlink() or manifest.is_symlink():
            raise CommandError(f"Refusing symlinked source path: apps/{name}")
        try:
            _validate_manifest(manifest, name)
            declaration = next(
                node.value
                for node in ast.parse(manifest.read_text(encoding="utf-8")).body
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "MODULE" for t in node.targets)
            )
            policy = next(
                (
                    ast.literal_eval(keyword.value)
                    for keyword in declaration.keywords
                    if keyword.arg == "migration_policy"
                ),
                "none",
            )
        except (OSError, SyntaxError, ValueError, KeyError, TypeError) as exc:
            raise CommandError(
                f"apps/{name}/manifest.py is not supported by this project's module "
                f"registry ({exc}). Upgrade this project's apps/core first; "
                "no modules installed."
            ) from exc
        ignore = _copy_ignore(module, policy)
        for current, directories, files in os.walk(module, followlinks=False):
            ignored = ignore(current, directories + files)
            for entry in (*directories, *files):
                if entry not in ignored and (Path(current) / entry).is_symlink():
                    relative = (Path(current) / entry).relative_to(apps).as_posix()
                    raise CommandError(f"Refusing symlinked source path: apps/{relative}")
            directories[:] = [entry for entry in directories if entry not in ignored]
        # A bundled owner without history must never get a regenerated schema.
        if policy == "bundled" and not any((module / "migrations").glob("[0-9]*.py")):
            raise CommandError(f"Bundled migrations missing for {name}")
        policies[name] = policy
    return policies


def _git(source: Path, *arguments: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(source), *arguments], capture_output=True, text=True, check=False
        )
    except OSError:  # Exported archives and minimal images may lack Git.
        return None
    return done.stdout if done.returncode == 0 else None


def _trusted_source_ref(source: Path, name: str, staged: Path) -> str | None:
    """Return HEAD only when it really is the ancestor of the installed bytes.

    Mirrors the generator's clean-Git-root rule for this one module, and also
    requires every installed file to equal its committed blob, which catches
    ignored files and index flags that ``git status`` does not report.
    """
    top = _git(source, "rev-parse", "--show-toplevel")
    head = (_git(source, "rev-parse", "--verify", "HEAD") or "").strip()
    if not top or Path(top.strip()).resolve() != source:
        return None
    if not re.fullmatch(r"[0-9a-f]{40,64}", head):
        return None
    prefix = f"apps/{name}/"
    dirty = _git(source, "status", "--porcelain=v1", "--untracked-files=all", "--", prefix)
    listing = _git(source, "ls-tree", "-r", "-z", "--full-tree", head, "--", prefix)
    if dirty is None or dirty.strip() or listing is None:
        return None
    committed = {}
    for record in filter(None, listing.split("\0")):
        details, path = record.split("\t", 1)
        mode, kind, blob = details.split()
        if kind != "blob" or mode not in {"100644", "100755"}:
            return None  # Committed symlinks or submodules are not plain source.
        committed[path.removeprefix(prefix)] = blob
    algorithm = "sha1" if len(head) == 40 else "sha256"
    for path in staged.rglob("*"):
        if not path.is_file():
            continue
        data = path.read_bytes()
        digest = hashlib.new(algorithm, b"blob %d\0" % len(data) + data).hexdigest()
        if committed.get(path.relative_to(staged).as_posix()) != digest:
            return None
    # A deleted runtime file would make the recorded snapshot differ from HEAD.
    runtime = {
        path
        for path in committed
        if path.endswith(".py") and not {"migrations", "tests"} & set(Path(path).parts)
    }
    return head if runtime == set(_module_fingerprint(staged)) else None


def _module_fingerprint(folder: Path) -> dict[str, str]:
    """Snapshot copied runtime Python files, matching the project generator."""
    return {
        path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*.py"))
        if not {"migrations", "tests", "__pycache__"} & set(path.parts)
    }


def _updated_origin(
    origin: Path, order: list[str], stage: Path, source: Path, policies: dict[str, str]
) -> str | None:
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
    # Older provenance has no per-module policies; start recording from now on.
    pinned = data.setdefault("module_migration_policies", {})
    if not isinstance(pinned, dict):
        raise CommandError("Invalid provenance migration policies; no modules installed.")
    # A leftover pin is a recorded history decision: never overwrite it silently.
    if set(order) & (set(included) | set(fingerprints) | set(pinned)):
        raise CommandError("Client provenance already names a module missing on disk.")
    pinned.update({name: policies[name] for name in order})

    for name in order:
        fingerprints[name] = _module_fingerprint(stage / name)
    data["included_apps"] = sorted(set(included) | set(order))
    module_refs = data.setdefault("module_source_refs", {})
    module_versions = data.setdefault("module_versions", {})
    if not isinstance(module_refs, dict) or not isinstance(module_versions, dict):
        raise CommandError("Invalid version tracking metadata; no modules installed.")
    source_version = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    for name in order:
        # Dirty or non-Git sources still install, but claim no immutable ancestor.
        source_ref = _trusted_source_ref(source, name, stage / name)
        if source_ref:
            module_refs[name] = source_ref
        module_versions[name] = source_version
    # Record schema mode on first installation. Never rewrite an existing pin.
    schema_modes = data.setdefault("schema_modes", {})
    if not isinstance(schema_modes, dict):
        raise CommandError("Invalid provenance schema_modes; no modules installed.")
    settings_file = origin.parent / "config" / "settings" / "base.py"
    for name in order:
        if name not in {"catalog", "inventory"} or name in schema_modes:
            continue
        if not settings_file.is_file():
            raise CommandError("Missing settings file for schema mode pinning.")
        tree = ast.parse(settings_file.read_text(encoding="utf-8"))
        values = [
            node.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == f"{name.upper()}_MODE"
                for target in node.targets
            )
        ]
        if len(values) != 1:
            raise CommandError(f"Cannot detect pinned {name} schema mode")
        try:
            mode = ast.literal_eval(values[0])
        except (SyntaxError, ValueError, TypeError) as exc:
            raise CommandError(f"Invalid {name} schema mode") from exc
        if mode not in {"tenant", "standalone"}:
            raise CommandError(f"Invalid {name} schema mode")
        schema_modes[name] = mode
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
        if (source / "apps").is_symlink():
            raise CommandError("Refusing symlinked source path: apps")
        # Read-only preflight, so --dry-run reports the same refusals.
        policies = _inspect_modules(source / "apps", order)
        self.stdout.write("Will install: " + ", ".join(order))
        if options["dry_run"]:
            return

        # Copy outside active module paths first. On failure, remove new folders.
        created = []
        try:
            with TemporaryDirectory(prefix=".primarykit-install-", dir=destination) as temp:
                stage = Path(temp)
                for name in order:
                    module = source / "apps" / name
                    # Never dereference a link that appears after the preflight.
                    shutil.copytree(
                        module,
                        stage / name,
                        ignore=_copy_ignore(module, policies[name]),
                        symlinks=True,
                    )
                # Validate the staged bytes themselves before anything is moved.
                if _inspect_modules(stage, order) != policies:
                    raise CommandError("Source manifests changed during installation.")
                final = existing | set(order)
                if "storage" in order and "organizations" not in final:
                    # Tenant test modules require optional Organizations models.
                    for name in ("test_storage.py", "test_seaweedfs_integration.py"):
                        (stage / "storage" / "tests" / name).unlink(missing_ok=True)
                origin = destination / "primarykit-origin.json"
                updated = _updated_origin(origin, order, stage, source, policies)
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
        client = [name for name in order if policies[name] == "client"]
        bundled = [name for name in order if policies[name] == "bundled"]
        steps = ["Installed: " + ", ".join(order) + ". Restart Django."]
        if client:
            steps.append(
                f"Run makemigrations {' '.join(client)}; review and commit the generated "
                "migrations in your project."
            )
        if bundled:
            steps.append(
                f"Bundled history shipped for: {', '.join(bundled)}; "
                "do not generate or edit migrations for them."
            )
        if client or bundled:
            steps.append("Then run migrate.")
        self.stdout.write(self.style.SUCCESS(" ".join(steps)))
