#!/usr/bin/env python3
"""Inspect or safely copy conflict-free module changes. No Django or network."""

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

CONTRACT_FILES = frozenset(
    {
        "manifest.py",
        "models.py",
        "urls.py",
        "domain.py",
        "services.py",
        "serializers.py",
        "permissions.py",
        "authentication.py",
        "views.py",
        "apps.py",
        "middleware.py",
        "signals.py",
        "jobs.py",
        "ports.py",
        "gateways.py",
    }
)
CONTRACT_PREFIXES = ("migrations/",)


def _hashes(folder: Path) -> dict[str, str]:
    if not folder.is_dir():
        return {}
    return {
        file.relative_to(folder).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sorted(folder.rglob("*.py"))
        if not {"migrations", "tests", "__pycache__"} & set(file.parts)
    }


def compare_modules(*, source: Path, project: Path) -> dict:
    """Never mutate either checkout, load arbitrary Python, or print file contents."""
    source = source.expanduser().resolve()
    project = project.expanduser().resolve()
    if source == project:
        raise ValueError("Source and target must be distinct repositories")
    if not (source / "apps" / "core" / "manifest.py").is_file():
        raise ValueError("Source is missing a PrimaryKit module catalog")
    origin = project / "primarykit-origin.json"
    if not origin.is_file():
        raise ValueError("Client provenance is missing; use manual Git diff review")
    metadata = json.loads(origin.read_text(encoding="utf-8"))
    baseline = metadata.get("module_fingerprints")
    installed = metadata.get("included_apps")
    if not isinstance(baseline, dict) or not isinstance(installed, list):
        raise ValueError("Client provenance has no baseline hashes; use manual Git diff")
    modules = {}
    for name in sorted(installed):
        if (
            not isinstance(name, str)
            or not name.isidentifier()
            or (name in baseline and not isinstance(baseline[name], dict))
        ):
            raise ValueError("Invalid provenance module metadata")
        if name not in baseline:
            # Older installers recorded the module name without an original
            # snapshot. Never invent an ancestor for a three-way comparison.
            modules[name] = {
                "changes": [
                    {
                        "path": "<baseline>",
                        "change": "baseline_unknown",
                        "contract_review": True,
                        "source_deleted": not (source / "apps" / name).is_dir(),
                        "client_deleted": not (project / "apps" / name).is_dir(),
                    }
                ],
                "needs_review": True,
            }
            continue
        before = baseline[name]
        current = _hashes(project / "apps" / name)
        incoming = _hashes(source / "apps" / name)
        changes = []
        for path in sorted(set(before) | set(current) | set(incoming)):
            if not isinstance(path, str) or not isinstance(before.get(path, ""), str):
                raise ValueError("Invalid provenance file metadata")
            original, local, remote = before.get(path), current.get(path), incoming.get(path)
            if local == remote:
                continue
            local_changed = local != original
            source_changed = remote != original
            if local_changed and source_changed:
                classification = "conflict_review"
            elif local_changed:
                classification = "client_modified"
            else:
                classification = "source_update"
            sensitive = path in CONTRACT_FILES or path.startswith(CONTRACT_PREFIXES)
            changes.append(
                {
                    "path": path,
                    "change": classification,
                    "contract_review": sensitive,
                    "source_deleted": remote is None,
                    "client_deleted": local is None,
                }
            )
        modules[name] = {"changes": changes, "needs_review": bool(changes)}
    return {
        "module_versions": metadata.get("module_versions", {}),
        "source_commit": metadata.get("source_commit"),
        "source": str(source),
        "project": str(project),
        "source_version_at_creation": metadata.get("source_version"),
        "modules": modules,
        "review_required": any(item["needs_review"] for item in modules.values()),
    }


def apply_safe_updates(*, source: Path, project: Path) -> dict:
    """Copy only conflict-free, non-contract Python changes into a client.

    Fails closed if *any* installed module requires review. This is not a
    schema migration, a dependency updater, or a three-way merge.
    """
    report = compare_modules(source=source, project=project)
    source, project = source.expanduser().resolve(), project.expanduser().resolve()
    operations = []
    blocked = []
    for module, info in report["modules"].items():
        for change in info["changes"]:
            path = change["path"]
            if (
                change["change"] != "source_update"
                or change["contract_review"]
                or change["source_deleted"]
            ):
                blocked.append(f"{module}/{path}: {change['change']}")
                continue
            source_file = source / "apps" / module / path
            target_file = project / "apps" / module / path
            source_root = (source / "apps" / module).resolve()
            target_root = (project / "apps" / module).resolve()
            if (
                not path.endswith(".py")
                or source_file.is_symlink()
                or target_file.is_symlink()
                or not source_file.resolve().is_relative_to(source_root)
                or not target_file.resolve().is_relative_to(target_root)
                or not source_file.is_file()
            ):
                blocked.append(f"{module}/{path}: unsafe path")
                continue
            operations.append((module, path, source_file, target_file))
    # Source migrations are excluded from the file fingerprints. Never silently
    # advance code while ignoring a newly introduced catalog schema history.
    for module in report["modules"]:
        migration_dir = source / "apps" / module / "migrations"
        if migration_dir.is_dir() and any(
            file.is_file() and file.name != "__init__.py" for file in migration_dir.glob("*.py")
        ):
            blocked.append(f"{module}/migrations: manual schema review required")
    if blocked:
        raise ValueError("Manual review required; no files changed: " + "; ".join(blocked))
    if not operations:
        return {"updated": [], "applied": False}

    origin = project / "primarykit-origin.json"
    metadata = json.loads(origin.read_text(encoding="utf-8"))
    fingerprints = metadata["module_fingerprints"]
    # Revalidate file hashes immediately before applying. A developer may have
    # changed the client after the report was prepared.
    for module, path, _, target_file in operations:
        expected = fingerprints[module].get(path)
        actual = (
            hashlib.sha256(target_file.read_bytes()).hexdigest() if target_file.is_file() else None
        )
        if expected != actual:
            raise ValueError(f"Client changed during update: {module}/{path}")

    with TemporaryDirectory(prefix=".primarykit-upgrade-", dir=project) as directory:
        stage = Path(directory)
        prepared = []
        for module, path, source_file, target_file in operations:
            staged_file = stage / "incoming" / module / path
            staged_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, staged_file, follow_symlinks=False)
            data_hash = hashlib.sha256(staged_file.read_bytes()).hexdigest()
            backup = stage / "backup" / module / path
            if target_file.is_file():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target_file, backup, follow_symlinks=False)
            prepared.append((module, path, staged_file, target_file, backup, data_hash))

        # Update provenance only after every file has been staged successfully.
        for module, path, _, _, _, data_hash in prepared:
            fingerprints[module][path] = data_hash
        staged_origin = stage / "primarykit-origin.json"
        staged_origin.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        applied = []
        created_dirs = []
        try:
            for _module, _path, staged_file, target_file, backup, _ in prepared:
                missing = []
                parent = target_file.parent
                while not parent.exists():
                    missing.append(parent)
                    parent = parent.parent
                for folder in reversed(missing):
                    folder.mkdir()
                    created_dirs.append(folder)
                os.replace(staged_file, target_file)
                applied.append((target_file, backup))
            os.replace(staged_origin, origin)
        except OSError:
            for target_file, backup in reversed(applied):
                if backup.is_file():
                    os.replace(backup, target_file)
                else:
                    target_file.unlink(missing_ok=True)
            for folder in reversed(created_dirs):
                folder.rmdir()
            raise
    return {
        "updated": [f"{module}/{path}" for module, path, *_ in operations],
        "applied": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only copied-module upgrade report")
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--three-way-plan", action="store_true", help="Read-only Git-backed merge assessment")
    parser.add_argument(
        "--apply-safe",
        action="store_true",
        help="Copy clean non-contract Python changes; abort on any conflict or contract change",
    )
    args = parser.parse_args(argv)
    result = (
        apply_safe_updates(source=args.source, project=args.project)
        if args.apply_safe
        else (
            three_way_plan(source=args.source, project=args.project)
            if args.three_way_plan
            else compare_modules(source=args.source, project=args.project)
        )
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.three_way_plan:
        for item in result["candidates"]:
            print(f"{item['module']}/{item['path']}: {item['reason'] or 'clean merge possible'}")
    elif args.apply_safe:
        print(f"Applied {len(result['updated'])} safe file update(s).")
    else:
        for name, info in result["modules"].items():
            for item in info["changes"]:
                level = "CONTRACT" if item["contract_review"] else "review"
                print(f"{name}/{item['path']}: {item['change']} ({level})")
        if not result["review_required"]:
            print("All installed module files match the source catalog.")
    return 0  # Report mode remains advisory; apply-safe is explicitly opt-in.


def three_way_plan(*, source: Path, project: Path) -> dict:
    """Assess mergeability using immutable Git blobs; never write client files."""
    report = compare_modules(source=source, project=project)
    source = source.expanduser().resolve()
    project = project.expanduser().resolve()
    meta = json.loads((project / "primarykit-origin.json").read_text(encoding="utf-8"))
    refs = meta.get("module_source_refs", {})
    fingerprints = meta["module_fingerprints"]
    results = []
    for module, data in report["modules"].items():
        for change in data["changes"]:
            if change["change"] != "conflict_review":
                continue
            path = change["path"]
            result = {"module": module, "path": path, "mergeable": False}
            results.append(result)
            if change["contract_review"] or change["source_deleted"] or change["client_deleted"]:
                result["reason"] = "contract_or_deletion"
                continue
            revision = refs.get(module) if isinstance(refs, dict) else None
            if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40,64}", revision):
                result["reason"] = "missing_immutable_baseline"
                continue
            if Path(path).is_absolute() or ".." in Path(path).parts or not path.endswith(".py"):
                result["reason"] = "invalid_path"
                continue
            original = subprocess.run(
                ["git", "-C", str(source), "show", f"{revision}:apps/{module}/{path}"],
                capture_output=True,
                check=False,
            )
            if original.returncode != 0:
                result["reason"] = "source_commit_unavailable"
                continue
            if hashlib.sha256(original.stdout).hexdigest() != fingerprints.get(module, {}).get(path):
                result["reason"] = "baseline_hash_mismatch"
                continue
            with TemporaryDirectory(prefix=".primarykit-merge-") as directory:
                folder = Path(directory)
                mine = folder / "mine.py"
                ancestor = folder / "ancestor.py"
                theirs = folder / "theirs.py"
                mine.write_bytes((project / "apps" / module / path).read_bytes())
                ancestor.write_bytes(original.stdout)
                theirs.write_bytes((source / "apps" / module / path).read_bytes())
                merged = subprocess.run(
                    ["git", "merge-file", "--stdout", str(mine), str(ancestor), str(theirs)],
                    capture_output=True,
                    check=False,
                )
                if merged.returncode != 0:
                    result["reason"] = "merge_conflict"
                else:
                    try:
                        ast.parse(merged.stdout.decode("utf-8"))
                    except (SyntaxError, UnicodeDecodeError):
                        result["reason"] = "merged_python_invalid"
                    else:
                        result["mergeable"] = True
                        result["reason"] = None
    return {"candidates": results, "all_mergeable": all(r["mergeable"] for r in results)}


if __name__ == "__main__":
    raise SystemExit(main())
