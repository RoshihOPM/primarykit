#!/usr/bin/env python3
"""Safe, read-only report of copied module changes. Requires no Django or network."""

import argparse
import hashlib
import json
from pathlib import Path

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
    }
)
CONTRACT_PREFIXES = ("migrations/",)


def _hashes(folder: Path) -> dict[str, str]:
    if not folder.is_dir():
        return {}
    return {
        file.relative_to(folder).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sorted(folder.rglob("*.py"))
        if "migrations" not in file.parts and "__pycache__" not in file.parts
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
            or name not in baseline
            or not isinstance(baseline[name], dict)
        ):
            raise ValueError("Invalid provenance module metadata")
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
        "source": str(source),
        "project": str(project),
        "source_version_at_creation": metadata.get("source_version"),
        "modules": modules,
        "review_required": any(item["needs_review"] for item in modules.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only copied-module upgrade report")
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = compare_modules(source=args.source, project=args.project)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        for name, info in result["modules"].items():
            for item in info["changes"]:
                level = "CONTRACT" if item["contract_review"] else "review"
                print(f"{name}/{item['path']}: {item['change']} ({level})")
        if not result["review_required"]:
            print("All installed module files match the source catalog.")
    return 0  # Drift is advisory; the checker is always read-only.


if __name__ == "__main__":
    raise SystemExit(main())
