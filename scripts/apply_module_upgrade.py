"""Opt-in, non-schema three-way upgrades in a clean client Git feature branch.

This tool never creates migrations, commits or PRs. Inspect and test the resulting
diff, then open a PR in the *client* repository before deployment.

Contract files (models, services, permissions, manifests...) are never written.
A maintainer who has reviewed and placed them by hand records that decision with
``accept_reviewed``; only then does the module's provenance advance.
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

from scripts.migration_adoption import _history, _policy
from scripts.module_upgrade import (
    _hashes,
    compare_modules,
    is_contract_path,
    source_differs_from_commit,
    three_way_plan,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


POLICIES = frozenset({"none", "client", "bundled"})


def _source_version(source: Path, revision: str) -> str | None:
    """Version of the immutable commit, never of an uncommitted pyproject.toml."""
    blob = subprocess.run(
        ["git", "-C", str(source), "show", f"{revision}:pyproject.toml"],
        check=False,
        capture_output=True,
    )
    if blob.returncode != 0:
        return None
    try:
        version = tomllib.loads(blob.stdout.decode("utf-8"))["project"]["version"]
    except (ValueError, KeyError, TypeError):
        return None
    return version if isinstance(version, str) and version else None


def _migration_pin(
    source_dir: Path, client_dir: Path, previous, *, keep_client_history: bool
) -> tuple[str | None, str | None]:
    """Decide which migration history an accepted module keeps. Never touches files.

    Fails closed: a differing history is retained as client-owned only when that
    was pinned before or is requested explicitly. It is never inferred, because
    an inferred ``client`` pin would hide an unmerged bundled migration.
    """
    policy = _policy(source_dir / "manifest.py")
    if not isinstance(policy, str) or policy not in POLICIES:
        return None, "source manifest has an invalid migration policy"
    if previous is not None and (not isinstance(previous, str) or previous not in POLICIES):
        return None, "client provenance has an invalid pinned migration policy"
    source_history = _history(source_dir / "migrations")
    if policy != "bundled":
        if source_history:
            return None, "source ships migrations without a bundled policy; manual review"
        if previous == "bundled":
            return None, "pinned bundled history no longer matches the source policy"
        return policy, None
    client_history = _history(client_dir / "migrations")
    if not client_history:
        return None, "client has no committed migration history to retain"
    if source_history == client_history:
        return ("client" if previous == "client" else "bundled"), None
    if previous == "client" or (keep_client_history and previous is None):
        return "client", None
    if previous == "bundled":
        return None, "bundled migration history differs; copy the reviewed source migrations first"
    return None, (
        "migration history differs from the bundled source; copy the reviewed source "
        "migrations or keep the applied client history with --keep-client-migrations"
    )


def apply_three_way_updates(
    *,
    source: Path,
    project: Path,
    accept_reviewed: tuple[str, ...] | frozenset[str] = (),
    merged_paths: tuple[str, ...] | frozenset[str] = (),
    keep_client_migrations: tuple[str, ...] | frozenset[str] = (),
) -> dict:
    """Merge non-contract Python and record explicitly reviewed contract changes.

    ``accept_reviewed`` names modules whose contract/schema changes a human has
    already reviewed and placed in the client. ``merged_paths`` (``module/path``)
    names hand-merged files in those modules that intentionally differ from the
    source. ``keep_client_migrations`` names accepted modules whose already applied,
    client-generated migration history is deliberately retained instead of the
    bundled source history. Reviewed contract files are never written; plain
    non-contract Python of an accepted module is still merged automatically.
    """
    source, project = source.resolve(), project.resolve()
    accepted = frozenset(accept_reviewed)
    merged_by_hand = frozenset(merged_paths)
    keep_history = frozenset(keep_client_migrations)
    if keep_history - accepted:
        raise ValueError(
            "--keep-client-migrations needs an accepted module: "
            + ", ".join(sorted(keep_history - accepted))
        )
    if _git(source, "rev-parse", "--show-toplevel") != str(source):
        raise ValueError("Expected source Git worktree root")
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
    foreign = source_differs_from_commit(
        source, [name for name in report["modules"] if (source / "apps" / name).is_dir()]
    )
    if foreign:
        raise ValueError("Source modules are not an immutable checkout: " + "; ".join(foreign))
    unknown = accepted - set(report["modules"])
    if unknown:
        raise ValueError(
            "Cannot accept modules that are not installed: " + ", ".join(sorted(unknown))
        )
    for item in merged_by_hand:
        module, _, path = item.partition("/")
        if module not in accepted or not path:
            raise ValueError(f"--merged-path needs an accepted module/path: {item}")
    plan = three_way_plan(source=source, project=project)
    candidates = {(r["module"], r["path"]): r for r in plan["candidates"]}
    origin = project / "primarykit-origin.json"
    if origin.is_symlink():
        raise ValueError("Symlinked client provenance is unsafe")
    before = origin.read_text(encoding="utf-8")
    metadata = json.loads(before)
    refs = metadata.get("module_source_refs")
    if not isinstance(refs, dict):
        raise ValueError("No per-module immutable ancestry")
    fingerprints = metadata["module_fingerprints"]
    pinned = metadata.get("module_migration_policies")
    if not isinstance(pinned, dict):
        pinned = {}
    pending = []
    recorded = []  # Reviewed by a human; provenance only, no file write.
    blocked = []
    pins = {}
    used_merged = set()
    verified_ancestry = set()

    def ancestry_error(module: str) -> str | None:
        ancestor_ref = refs.get(module)
        if not isinstance(ancestor_ref, str) or not re.fullmatch(r"[0-9a-f]{40,64}", ancestor_ref):
            return "missing immutable source ancestry"
        if module not in verified_ancestry:
            ancestor = subprocess.run(
                ["git", "-C", str(source), "merge-base", "--is-ancestor", ancestor_ref, revision],
                check=False,
                capture_output=True,
            )
            if ancestor.returncode != 0:
                return "source ancestry is not available"
            verified_ancestry.add(module)
        return None

    def baseline_error(module: str, path: str) -> str | None:
        """Source-only and reviewed changes need the same trusted ancestry as merges.

        Never apply or record from an unrelated checkout or forged origin.
        """
        error = ancestry_error(module)
        if error:
            return error
        baseline_hash = fingerprints[module].get(path)
        baseline_blob = subprocess.run(
            ["git", "-C", str(source), "show", f"{refs[module]}:apps/{module}/{path}"],
            check=False,
            capture_output=True,
        )
        if baseline_hash is None:
            # An untracked fingerprint does not make an old source file new.
            # The path must genuinely be absent from the immutable ancestor.
            if baseline_blob.returncode == 0:
                return "omitted historical source fingerprint"
        elif (
            baseline_blob.returncode != 0
            or hashlib.sha256(baseline_blob.stdout).hexdigest() != baseline_hash
        ):
            return "historical baseline does not match"
        return None

    for module, detail in report["modules"].items():
        directory = source / "apps" / module
        is_accepted = module in accepted
        if is_accepted:
            if not isinstance(fingerprints.get(module), dict):
                blocked.append(f"{module}: unknown baseline cannot be accepted")
                continue
            try:
                pin, problem = _migration_pin(
                    directory,
                    project / "apps" / module,
                    pinned.get(module),
                    keep_client_history=module in keep_history,
                )
            except (OSError, ValueError, SyntaxError, TypeError, RecursionError) as exc:
                pin, problem = None, str(exc)
            if problem:
                blocked.append(f"{module}: {problem}")
            else:
                pins[module] = pin
            error = ancestry_error(module)
            if error:
                blocked.append(f"{module}: {error}")
                continue
        elif (
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
            key = f"{module}/{path}"
            if kind == "client_modified":
                continue
            needs_review = change["contract_review"] or change["source_deleted"]
            if (
                not path.endswith(".py")
                or Path(path).is_absolute()
                or ".." in Path(path).parts
                or (needs_review and not is_accepted)
            ):
                blocked.append(f"{key}: contract/deletion review required")
                continue
            incoming = directory / path
            target = project / "apps" / module / path
            if needs_review or (kind == "conflict_review" and key in merged_by_hand):
                # Accepted module: the client bytes were placed by a reviewer.
                if kind != "conflict_review":
                    blocked.append(
                        f"{key}: place the reviewed source change in the client before accepting"
                    )
                    continue
                if key not in merged_by_hand:
                    blocked.append(f"{key}: merge manually and confirm with --merged-path")
                    continue
                if incoming.is_symlink() or target.is_symlink():
                    blocked.append(f"{key}: unsafe path")
                    continue
                error = baseline_error(module, path)
                if error:
                    blocked.append(f"{key}: {error}")
                    continue
                used_merged.add(key)
                recorded.append(
                    (
                        module,
                        path,
                        hashlib.sha256(incoming.read_bytes()).hexdigest()
                        if incoming.is_file()
                        else None,
                    )
                )
                continue
            if (
                incoming.is_symlink()
                or target.is_symlink()
                or not incoming.is_file()
                or not incoming.resolve().is_relative_to(directory)
                or not target.resolve().is_relative_to(project / "apps" / module)
            ):
                blocked.append(f"{key}: unsafe path")
                continue
            error = baseline_error(module, path)
            if error:
                blocked.append(f"{key}: {error}")
                continue
            upstream = incoming.read_bytes()
            merged = upstream
            if kind == "conflict_review":
                candidate = candidates.get((module, path))
                if not candidate or not candidate["mergeable"]:
                    blocked.append(f"{key}: unresolved merge")
                    continue
                original = subprocess.run(
                    ["git", "-C", str(source), "show", f"{refs[module]}:apps/{module}/{path}"],
                    check=True,
                    capture_output=True,
                ).stdout
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
                        blocked.append(f"{key}: merge conflict")
                        continue
                    merged = merge.stdout
            try:
                ast.parse(merged.decode("utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                blocked.append(f"{key}: merged Python invalid")
                continue
            pending.append((module, path, target, merged, upstream))

    for key in sorted(merged_by_hand - used_merged):
        blocked.append(f"{key}: --merged-path does not match a reviewed two-sided change")

    # Files already manually accepted by the client are absent from the diff
    # when local bytes match incoming bytes. If another file in this module is
    # being upgraded, preserve ancestry for those converged files as well.
    # Otherwise a later upgrade sees a new source commit but stale base hashes.
    converged = []
    for module in sorted({name for name, *_ in pending} | accepted):
        baseline = fingerprints.get(module)
        if not isinstance(baseline, dict):
            continue
        incoming_hashes = _hashes(source / "apps" / module)
        client_hashes = _hashes(project / "apps" / module)
        for path in sorted(set(incoming_hashes) | set(baseline)):
            current_hash = incoming_hashes.get(path)
            original_hash = baseline.get(path)
            if current_hash == original_hash or client_hashes.get(path) != current_hash:
                continue
            if module not in accepted:
                # Without an explicit acceptance a byte-identical contract is
                # still an unreviewed schema/behavior change.
                if current_hash is None:
                    blocked.append(f"{module}/{path}: converged deletion needs review")
                    continue
                if is_contract_path(path):
                    blocked.append(f"{module}/{path}: converged contract needs review")
                    continue
            error = baseline_error(module, path)
            if error:
                blocked.append(
                    f"{module}/{path}: "
                    + (
                        "converged baseline mismatch"
                        if "historical" in error
                        else f"converged file has {error}"
                    )
                )
                continue
            converged.append((module, path, current_hash))

    version = _source_version(source, revision)
    if accepted and (version is None or not isinstance(metadata.get("module_versions"), dict)):
        blocked.append("source or client module version is unreadable; cannot record acceptance")
    if blocked:
        raise ValueError("Review required; no changes applied: " + "; ".join(sorted(blocked)))
    if not pending and not accepted:
        return {"applied": False, "updated": [], "accepted": [], "branch": branch}

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
        for module, path, digest in (*recorded, *converged):
            if digest is None:
                fingerprints[module].pop(path, None)
            else:
                fingerprints[module][path] = digest
        versions = metadata.get("module_versions")
        for module in sorted({name for name, *_ in pending} | accepted):
            refs[module] = revision
            if version is not None and isinstance(versions, dict):
                versions[module] = version
        if pins:
            pinned.update(pins)
            metadata["module_migration_policies"] = pinned
        if not prepared and metadata == json.loads(before):
            # Accepting an already current module must not claim any work.
            return {"applied": False, "updated": [], "accepted": [], "branch": branch}
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
        "accepted": sorted(accepted),
        "reviewed_paths": sorted(
            f"{m}/{path}" for m, path, _ in (*recorded, *converged) if m in accepted
        ),
        "migration_policies": pins,
        "branch": branch,
        "requires_client_pr": True,
    }
