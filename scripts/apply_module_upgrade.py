"""Opt-in, non-schema three-way upgrades in a clean client Git feature branch.

This tool never creates migrations, commits or PRs. Inspect and test the resulting
diff, then open a PR in the *client* repository before deployment.
"""

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.module_upgrade import CONTRACT_FILES, _hashes, compare_modules, three_way_plan


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def apply_three_way_updates(*, source: Path, project: Path) -> dict:
    source, project = source.resolve(), project.resolve()
    if _git(project, "rev-parse", "--show-toplevel") != str(project):
        raise ValueError("Expected client Git worktree root")
    branch = _git(project, "branch", "--show-current")
    if not branch or branch in {"main", "master", "dev", "develop"}:
        raise ValueError("Create a dedicated client feature branch before applying")
    if _git(project, "status", "--porcelain"):
        raise ValueError("Client worktree has uncommitted changes")
    if _git(source, "status", "--porcelain", "--", "apps"):
        raise ValueError("Source modules are not an immutable checkout")
    revision = _git(source, "rev-parse", "--verify", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
        raise ValueError("Missing immutable source SHA")
    report = compare_modules(source=source, project=project)
    plan = three_way_plan(source=source, project=project)
    candidates = {(r["module"], r["path"]): r for r in plan["candidates"]}
    origin = project / "primarykit-origin.json"
    metadata = json.loads(origin.read_text(encoding="utf-8"))
    refs = metadata.get("module_source_refs")
    if not isinstance(refs, dict):
        raise ValueError("No per-module immutable ancestry")
    fingerprints = metadata["module_fingerprints"]
    pending = []
    blocked = []
    verified_ancestry = set()

    for module, detail in report["modules"].items():
        directory = source / "apps" / module
        if (
            detail["changes"]
            and (directory / "migrations").is_dir()
            and any(
                f.is_file() and f.name != "__init__.py"
                for f in (directory / "migrations").glob("*.py")
            )
        ):
            blocked.append(f"{module}: reviewed schema adoption required")
        for change in detail["changes"]:
            path = change["path"]
            kind = change["change"]
            if kind == "client_modified":
                continue
            if (
                change["contract_review"]
                or change["source_deleted"]
                or not path.endswith(".py")
                or Path(path).is_absolute()
                or ".." in Path(path).parts
            ):
                blocked.append(f"{module}/{path}: contract/deletion review required")
                continue
            incoming = directory / path
            target = project / "apps" / module / path
            if (
                incoming.is_symlink()
                or target.is_symlink()
                or not incoming.is_file()
                or not incoming.resolve().is_relative_to(directory)
                or not target.resolve().is_relative_to(project / "apps" / module)
            ):
                blocked.append(f"{module}/{path}: unsafe path")
                continue
            # Source-only changes require the same trusted ancestry as three-way
            # conflicts. Never apply from an unrelated checkout or forged origin.
            ancestor_ref = refs.get(module)
            if not isinstance(ancestor_ref, str) or not re.fullmatch(
                r"[0-9a-f]{40,64}", ancestor_ref
            ):
                blocked.append(f"{module}/{path}: missing immutable source ancestry")
                continue
            if module not in verified_ancestry:
                ancestor = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(source),
                        "merge-base",
                        "--is-ancestor",
                        ancestor_ref,
                        revision,
                    ],
                    check=False,
                    capture_output=True,
                )
                if ancestor.returncode != 0:
                    blocked.append(f"{module}/{path}: source ancestry is not available")
                    continue
                verified_ancestry.add(module)
            baseline_hash = fingerprints[module].get(path)
            if baseline_hash is not None:
                baseline_blob = subprocess.run(
                    ["git", "-C", str(source), "show", f"{ancestor_ref}:apps/{module}/{path}"],
                    check=False,
                    capture_output=True,
                )
                if (
                    baseline_blob.returncode != 0
                    or hashlib.sha256(baseline_blob.stdout).hexdigest() != baseline_hash
                ):
                    blocked.append(f"{module}/{path}: historical baseline does not match")
                    continue
            upstream = incoming.read_bytes()
            merged = upstream
            if kind == "conflict_review":
                candidate = candidates.get((module, path))
                if not candidate or not candidate["mergeable"]:
                    blocked.append(f"{module}/{path}: unresolved merge")
                    continue
                ancestor_ref = refs.get(module)
                if not isinstance(ancestor_ref, str):
                    blocked.append(f"{module}/{path}: missing source ref")
                    continue
                original = subprocess.run(
                    ["git", "-C", str(source), "show", f"{ancestor_ref}:apps/{module}/{path}"],
                    check=True,
                    capture_output=True,
                ).stdout
                if hashlib.sha256(original).hexdigest() != fingerprints[module].get(path):
                    blocked.append(f"{module}/{path}: corrupted ancestor")
                    continue
                with TemporaryDirectory(prefix="primarykit-three-way-") as td:
                    files = [Path(td) / x for x in ("client.py", "base.py", "source.py")]
                    for filename, data in zip(
                        files, (target.read_bytes(), original, upstream), strict=True
                    ):
                        filename.write_bytes(data)
                    merge = subprocess.run(
                        ["git", "merge-file", "--stdout", *(str(p) for p in files)],
                        check=False,
                        capture_output=True,
                    )
                    if merge.returncode:
                        blocked.append(f"{module}/{path}: merge conflict")
                        continue
                    merged = merge.stdout
            try:
                ast.parse(merged.decode("utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                blocked.append(f"{module}/{path}: merged Python invalid")
                continue
            pending.append((module, path, target, merged, upstream))

    # Files already manually accepted by the client are absent from the diff
    # when local bytes match incoming bytes. If another file in this module is
    # being upgraded, preserve ancestry for those converged files as well.
    # Otherwise a later upgrade sees a new source commit but stale base hashes.
    converged = []
    for module in sorted({name for name, *_ in pending}):
        incoming_hashes = _hashes(source / "apps" / module)
        client_hashes = _hashes(project / "apps" / module)
        ancestor_ref = refs[module]
        baseline = fingerprints[module]
        for path in sorted(set(incoming_hashes) | set(baseline)):
            current_hash = incoming_hashes.get(path)
            original_hash = baseline.get(path)
            if current_hash == original_hash or client_hashes.get(path) != current_hash:
                continue
            if current_hash is None:
                blocked.append(f"{module}/{path}: converged deletion needs review")
                continue
            if path in CONTRACT_FILES:
                blocked.append(f"{module}/{path}: converged contract needs review")
                continue
            history = subprocess.run(
                ["git", "-C", str(source), "show", f"{ancestor_ref}:apps/{module}/{path}"],
                check=False,
                capture_output=True,
            )
            if original_hash is None:
                valid_history = history.returncode != 0
            else:
                valid_history = (
                    history.returncode == 0
                    and hashlib.sha256(history.stdout).hexdigest() == original_hash
                )
            if not valid_history:
                blocked.append(f"{module}/{path}: converged baseline mismatch")
                continue
            converged.append((module, path, current_hash))

    if blocked:
        raise ValueError("Review required; no changes applied: " + "; ".join(sorted(blocked)))
    if not pending:
        return {"applied": False, "updated": [], "branch": branch}

    # All candidate writes are prepared before mutating any client file.
    with TemporaryDirectory(prefix=".primarykit-apply-", dir=project) as td:
        stage = Path(td)
        prepared = []
        for module, path, target, merged, upstream in pending:
            new = stage / "incoming" / module / path
            new.parent.mkdir(parents=True, exist_ok=True)
            new.write_bytes(merged)
            backup = stage / "backup" / module / path
            if target.is_file():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            prepared.append((module, path, new, target, backup, upstream))
        for module, path, _, _, _, upstream in prepared:
            fingerprints[module][path] = hashlib.sha256(upstream).hexdigest()
            refs[module] = revision
        for module, path, digest in converged:
            fingerprints[module][path] = digest
        new_origin = stage / "primarykit-origin.json"
        new_origin.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        applied = []
        created = []
        try:
            for _, _, src, target, backup, _ in prepared:
                missing = []
                folder = target.parent
                while not folder.exists():
                    missing.append(folder)
                    folder = folder.parent
                for folder in reversed(missing):
                    folder.mkdir()
                    created.append(folder)
                os.replace(src, target)
                applied.append((target, backup))
            os.replace(new_origin, origin)
        except OSError:
            for target, backup in reversed(applied):
                if backup.is_file():
                    os.replace(backup, target)
                else:
                    target.unlink(missing_ok=True)
            for folder in reversed(created):
                folder.rmdir()
            raise
    return {
        "applied": True,
        "updated": [f"{m}/{path}" for m, path, *_ in pending],
        "branch": branch,
        "requires_client_pr": True,
    }
