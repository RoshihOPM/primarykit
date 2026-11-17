#!/usr/bin/env python3
"""Upgrade a client generated from an immutable historical baseline on PostgreSQL.

For one pinned baseline commit this builds a detached client with that
revision's own generator, migrates and seeds a real PostgreSQL database,
customizes client files, then upgrades the copied modules to the current
catalog and proves that rows, client edits and the migration ledger survive.

It is CI evidence for the upgrade tooling, not a production migration tool.
The scripted "reviewer" below stands in for the human who must read every
contract diff in a real client pull request.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.apply_module_upgrade import apply_three_way_updates  # noqa: E402
from scripts.migration_adoption import adoption_plan  # noqa: E402
from scripts.module_upgrade import compare_modules  # noqa: E402

REGISTRY = ROOT / "scripts" / "release_baselines.json"
SETTINGS = "--settings=config.settings.postgres_test"
GIT_IDENTITY = ("-c", "user.name=PrimaryKit CI", "-c", "user.email=ci@example.test")
CLIENT_MARKER = "# client customization kept across upgrades\n"
# Client edits: one contract file and one plain helper that upstream also changed.
CUSTOMIZED = ("orders/services.py", "kanban/services.py", "inventory/standalone_views.py")

SEED = (
    "from apps.users.models import User; "
    "from apps.tasks.models import BackgroundJob; "
    "from apps.orders.services import place_order; "
    "from apps.payments.services import create_intent; "
    "BackgroundJob.objects.create(namespace='release-upgrade', code='preserve.row', "
    "payload={'probe': True}, max_attempts=1); "
    "owner=User.objects.create_user(email='release-upgrade@example.test', "
    "password='smoke-test-only'); "
    "order=place_order(actor=owner, currency='USD', lines=[{'sku': 'book', "
    "'title': 'Book', 'quantity': 1, 'unit_price_minor': 235}], "
    "idempotency_key='release-upgrade-order'); "
    "create_intent(actor=owner, amount_minor=235, currency='USD', "
    "source_order_id=order.pk, idempotency_key='release-upgrade-payment')"
)
VERIFY = (
    "from apps.users.models import User; "
    "from apps.tasks.models import BackgroundJob; "
    "from apps.orders.models import Order, OrderItem; "
    "from apps.payments.models import PaymentIntent; "
    "assert BackgroundJob.objects.filter(namespace='release-upgrade', "
    "code='preserve.row', payload={'probe': True}).count() == 1; "
    "owner=User.objects.get(email='release-upgrade@example.test'); "
    "order=Order.objects.get(owner=owner, idempotency_key='release-upgrade-order'); "
    "assert order.total_minor == 235 and order.status == 'placed'; "
    "assert OrderItem.objects.filter(order=order, sku='BOOK', "
    "line_total_minor=235).count() == 1; "
    "assert PaymentIntent.objects.filter(owner=owner, source_order_id=order.pk, "
    "amount_minor=235, status='pending', "
    "idempotency_key='release-upgrade-payment').count() == 1"
)


def load_baselines(path: Path = REGISTRY) -> tuple[tuple[str, ...], dict[str, str]]:
    """Validate the registry; a moved tag or abbreviated SHA is never a baseline."""
    data = json.loads(path.read_text(encoding="utf-8"))
    apps, entries = data.get("apps"), data.get("baselines")
    if (
        not isinstance(apps, list)
        or not apps
        or any(not isinstance(app, str) or not app.isidentifier() for app in apps)
        or not isinstance(entries, list)
    ):
        raise ValueError("Invalid release baseline registry")
    baselines: dict[str, str] = {}
    for entry in entries:
        identifier = entry.get("id") if isinstance(entry, dict) else None
        commit = entry.get("commit") if isinstance(entry, dict) else None
        if (
            not isinstance(identifier, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,62}", identifier)
            or not isinstance(commit, str)
            or not re.fullmatch(r"[0-9a-f]{40}", commit)
            or identifier in baselines
            or commit in baselines.values()
        ):
            raise ValueError("Baselines need unique ids and full immutable commit SHAs")
        baselines[identifier] = commit
    if len(baselines) < 3:
        raise ValueError("At least three release baselines are required")
    return tuple(apps), baselines


def _run(cwd: Path, *command: str, capture: bool = False) -> str:
    result = subprocess.run(
        command, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE if capture else None
    )
    return result.stdout.strip() if capture else ""


def _git(cwd: Path, *args: str) -> str:
    return _run(cwd, "git", *GIT_IDENTITY, *args, capture=True)


def _commit(cwd: Path, message: str) -> None:
    _git(cwd, "add", "-A")
    if _git(cwd, "status", "--porcelain"):
        _git(cwd, "commit", "-q", "-m", message)


def _manage(client: Path, *args: str) -> None:
    _run(client, "uv", "run", "python", "manage.py", *args, SETTINGS)


def place_reviewed_contracts(*, source: Path, client: Path) -> tuple[set[str], set[str]]:
    """Scripted stand-in for the human contract review of a client pull request.

    Upstream-only contract changes are copied; two-sided ones are merged with
    Git and must merge cleanly. Returns (accepted modules, hand-merged paths).
    """
    report = compare_modules(source=source, project=client)
    refs = json.loads((client / "primarykit-origin.json").read_text(encoding="utf-8"))[
        "module_source_refs"
    ]
    accepted: set[str] = set()
    merged: set[str] = set()
    for module, detail in report["modules"].items():
        for change in detail["changes"]:
            if not change["contract_review"] or change["change"] == "client_modified":
                continue
            path = change["path"]
            incoming = source / "apps" / module / path
            target = client / "apps" / module / path
            accepted.add(module)
            if change["source_deleted"]:
                raise RuntimeError(f"Scripted review cannot decide deletion of {module}/{path}")
            if change["change"] == "source_update":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(incoming.read_bytes())
                continue
            with TemporaryDirectory(prefix="primarykit-review-") as work:
                base = Path(work) / "base.py"
                base.write_bytes(
                    subprocess.run(
                        ["git", "-C", str(source), "show", f"{refs[module]}:apps/{module}/{path}"],
                        check=True,
                        capture_output=True,
                    ).stdout
                )
                # Rewrites the client file in place; a conflict fails the job.
                _run(client, "git", "merge-file", str(target), str(base), str(incoming))
            merged.add(f"{module}/{path}")
    return accepted, merged


def sync_unmodified_support_files(
    *, source: Path, client: Path, previous_refs: dict, baseline: str, head: str
) -> list:
    """Port upstream tests and agent guidance; never touch client-edited files.

    Tests and agent instructions are outside the provenance fingerprints, so the
    upgrader leaves them alone, yet a stale copied test asserts the old contract.
    Only files byte-identical to the baseline blob are replaced, and agent files
    new since the baseline are added. This stands in for the reviewer who ports
    such changes by hand in a real client pull request.
    """
    current = json.loads((client / "primarykit-origin.json").read_text(encoding="utf-8"))[
        "module_source_refs"
    ]

    def tracked(revision: str, prefix: str) -> set[str]:
        listing = subprocess.run(
            ["git", "-C", str(source), "ls-tree", "-r", "--name-only", revision, "--", prefix],
            check=True,
            capture_output=True,
            text=True,
        )
        return set(listing.stdout.splitlines())

    candidates: dict[str, str] = {}
    for module, old in sorted(previous_refs.items()):
        if current.get(module) == head and old != head:
            for relative in tracked(old, f"apps/{module}/tests"):
                candidates[relative] = old
    for prefix in ("AGENTS.md", ".agents"):
        for relative in tracked(baseline, prefix) | tracked(head, prefix):
            candidates[relative] = baseline

    replaced = []
    for relative, old in sorted(candidates.items()):
        target, incoming = client / relative, source / relative
        if target.is_symlink() or incoming.is_symlink() or not incoming.is_file():
            continue
        blob = subprocess.run(
            ["git", "-C", str(source), "show", f"{old}:{relative}"],
            check=False,
            capture_output=True,
        )
        unchanged_copy = (
            blob.returncode == 0 and target.is_file() and target.read_bytes() == blob.stdout
        )
        new_agent_file = (
            blob.returncode != 0 and not target.exists() and relative.startswith(".agents/")
        )
        if (unchanged_copy and incoming.read_bytes() != blob.stdout) or new_agent_file:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(incoming.read_bytes())
            replaced.append(relative)
    return replaced


def run_baseline(identifier: str) -> None:
    apps, baselines = load_baselines()
    if identifier not in baselines:
        raise ValueError(f"Unknown release baseline: {identifier}")
    if not os.environ.get("DATABASE_URL", "").startswith("postgresql://"):
        raise RuntimeError("Explicit PostgreSQL DATABASE_URL is required")
    commit = baselines[identifier]
    if _git(ROOT, "status", "--porcelain", "--untracked-files=all", "--", "apps"):
        raise RuntimeError("Current catalog modules must be a clean committed checkout")
    head = _git(ROOT, "rev-parse", "--verify", "HEAD")
    ancestor = subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, head], check=False
    )
    if ancestor.returncode != 0:
        raise RuntimeError(
            f"Baseline {identifier} is not an ancestor of HEAD; fetch the full Git history"
        )

    with TemporaryDirectory(prefix="primarykit-release-upgrade-") as work:
        baseline, client = Path(work) / "baseline", Path(work) / "upgrade-client"
        _git(ROOT, "worktree", "add", "--quiet", "--detach", str(baseline), commit)
        try:
            # The historical generator itself creates the client and its provenance.
            _run(
                baseline,
                sys.executable,
                "scripts/new_project.py",
                str(client),
                "--name",
                "upgrade-client",
                "--apps",
                *apps,
                "--git-init",
            )
        finally:
            _git(ROOT, "worktree", "remove", "--force", str(baseline))

        origin = client / "primarykit-origin.json"
        recorded = json.loads(origin.read_text(encoding="utf-8"))
        if recorded.get("source_commit") != commit:
            raise RuntimeError("Historical generator did not record the baseline commit")

        _run(client, "uv", "sync", "--locked", "--all-groups")
        labels = _run(client, "uv", "run", "python", "-m", "apps.core.migration_plan", capture=True)
        _manage(client, "makemigrations", *labels.split(), "--noinput")
        _manage(client, "migrate", "--noinput")
        _manage(client, "shell", "-c", SEED)
        _commit(client, "Baseline client with its own migrations")

        for relative in CUSTOMIZED:
            path = client / "apps" / relative
            path.write_text(path.read_text(encoding="utf-8") + CLIENT_MARKER, encoding="utf-8")
        _commit(client, "Client customizations")
        ledger_before = _run(
            client,
            "uv",
            "run",
            "python",
            "manage.py",
            "showmigrations",
            "--plan",
            SETTINGS,
            capture=True,
        )

        _git(client, "switch", "-q", "-c", "chore/primarykit-upgrade")
        accepted, merged = place_reviewed_contracts(source=ROOT, client=client)
        _commit(client, "Reviewed contract changes from the source catalog")
        # A client that already applied its own history keeps it; nothing is faked.
        keep_history = {
            item["module"]
            for item in adoption_plan(source=ROOT, project=client)["modules"]
            if item["status"] == "manual_adoption_required" and item["module"] in accepted
        }
        result = apply_three_way_updates(
            source=ROOT,
            project=client,
            accept_reviewed=tuple(sorted(accepted)),
            merged_paths=tuple(sorted(merged)),
            keep_client_migrations=tuple(sorted(keep_history)),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        _commit(client, "Upgrade copied PrimaryKit modules")
        ported = sync_unmodified_support_files(
            source=ROOT,
            client=client,
            previous_refs=recorded["module_source_refs"],
            baseline=commit,
            head=head,
        )
        print("Ported unmodified upstream support files:", ", ".join(ported) or "none")
        _commit(client, "Port upstream tests and agent guidance")

        for relative in CUSTOMIZED:
            if CLIENT_MARKER not in (client / "apps" / relative).read_text(encoding="utf-8"):
                raise RuntimeError(f"Client customization lost: {relative}")
        remaining = compare_modules(source=ROOT, project=client)
        leftovers = [
            f"{module}/{change['path']}: {change['change']}"
            for module, detail in remaining["modules"].items()
            for change in detail["changes"]
            if change["change"] != "client_modified"
        ]
        if leftovers:
            raise RuntimeError("Upgrade left unreviewed source changes: " + "; ".join(leftovers))
        upgraded = json.loads(origin.read_text(encoding="utf-8"))
        for module in recorded["included_apps"]:
            folder = ROOT / "apps" / module
            for path, digest in upgraded["module_fingerprints"][module].items():
                if upgraded["module_source_refs"][module] != head:
                    break  # Untouched module: still anchored to the baseline commit.
                if hashlib.sha256((folder / path).read_bytes()).hexdigest() != digest:
                    raise RuntimeError(f"Provenance does not match source: {module}/{path}")

        # Schema follow-up is client-owned: generate, apply and keep new migrations.
        _manage(client, "makemigrations", "--noinput")
        _commit(client, "Client-owned migrations after the module upgrade")
        _manage(client, "migrate", "--noinput")
        ledger_after = _run(
            client,
            "uv",
            "run",
            "python",
            "manage.py",
            "showmigrations",
            "--plan",
            SETTINGS,
            capture=True,
        )
        if not set(ledger_before.splitlines()) <= set(ledger_after.splitlines()):
            raise RuntimeError("Previously applied client migrations changed during upgrade")
        _manage(client, "shell", "-c", VERIFY)
        _manage(client, "makemigrations", "--check", "--dry-run")
        _run(
            client,
            "uv",
            "run",
            "python",
            str(ROOT / "scripts" / "migration_adoption.py"),
            "--source",
            str(ROOT),
            "--project",
            str(client),
            "--verify-postgres",
            "--strict",
        )
        _run(client, "uv", "run", "python", "-m", "apps.core.doctor", "--strict")
        _manage(client, "check")
        _run(client, "uv", "run", "pytest", "-q", "--ds=config.settings.postgres_test")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="Baseline id from the registry")
    run_baseline(parser.parse_args().baseline)


if __name__ == "__main__":
    main()
