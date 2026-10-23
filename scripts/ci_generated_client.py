#!/usr/bin/env python3
"""Build independent generated clients on PostgreSQL in CI."""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.new_project import OPTIONAL_APPS, create_project  # noqa: E402

CASES = {
    "minimal": {"preset": "minimal"},
    "api_keys": {"apps": ("api_keys",)},
    "tasks": {"apps": ("tasks",)},
    "webhooks": {"apps": ("webhooks",)},
    "listings": {"apps": ("listings",)},
    "marketplace": {"preset": "marketplace"},
    "commerce": {"preset": "commerce"},
    "crm": {"preset": "crm"},
    "all": {"apps": tuple(sorted(OPTIONAL_APPS))},
}


def run_case(case: str) -> None:
    """Use PostgreSQL: schema drift and failing client tests fail the CI job."""
    if case not in CASES:
        raise ValueError(f"Unknown matrix case: {case}")
    if not os.environ.get("DATABASE_URL", "").startswith("postgresql://"):
        raise RuntimeError("Explicit PostgreSQL DATABASE_URL is required")
    options = CASES[case]
    with TemporaryDirectory(prefix="primarykit-ci-") as work_dir:
        project_name = "smoke-" + case.replace("_", "-")
        target = Path(work_dir) / project_name
        create_project(
            target,
            name=project_name,
            optional_apps=set(options.get("apps", ())),
            preset=options.get("preset"),
        )

        def run(*command: str, capture: bool = False) -> str:
            result = subprocess.run(
                command,
                cwd=target,
                check=True,
                text=True,
                stdout=subprocess.PIPE if capture else None,
            )
            return result.stdout.strip() if capture else ""

        run("uv", "sync", "--locked", "--all-groups")
        run("uv", "run", "python", "-m", "apps.core.doctor", "--strict")
        labels = run("uv", "run", "python", "-m", "apps.core.migration_plan", capture=True)
        if labels:
            run(
                "uv",
                "run",
                "python",
                "manage.py",
                "makemigrations",
                *labels.split(),
                "--noinput",
                "--settings=config.settings.postgres_test",
            )
        run(
            "uv",
            "run",
            "python",
            "manage.py",
            "migrate",
            "--noinput",
            "--settings=config.settings.postgres_test",
        )
        # Versioned Tasks 0001 must retain real rows across repeated migrations.
        # This is a stateful idempotency smoke, NOT an historical upgrade claim.
        if (target / "apps" / "tasks" / "models.py").exists():
            run(
                "uv",
                "run",
                "python",
                "manage.py",
                "shell",
                "--settings=config.settings.postgres_test",
                "-c",
                "from apps.tasks.models import BackgroundJob; "
                "BackgroundJob.objects.create("
                "namespace='primarykit-upgrade-smoke', code='preserve.row', "
                "payload={'probe': True}, max_attempts=1)",
            )
            run(
                "uv",
                "run",
                "python",
                "manage.py",
                "migrate",
                "--noinput",
                "--settings=config.settings.postgres_test",
            )
            run(
                "uv",
                "run",
                "python",
                "manage.py",
                "shell",
                "--settings=config.settings.postgres_test",
                "-c",
                "from apps.tasks.models import BackgroundJob; "
                "assert BackgroundJob.objects.filter("
                "namespace='primarykit-upgrade-smoke', code='preserve.row', "
                "payload={'probe': True}).count() == 1",
            )

        # Preserve linked commerce rows across repeated migrations in detached
        # PostgreSQL clients. This checks idempotency, not cross-version upgrades.
        if all((target / "apps" / name / "models.py").is_file() for name in ("orders", "payments")):
            run(
                "uv",
                "run",
                "python",
                "manage.py",
                "shell",
                "--settings=config.settings.postgres_test",
                "-c",
                "from apps.users.models import User; "
                "from apps.orders.services import place_order; "
                "from apps.payments.services import create_intent; "
                "owner=User.objects.create_user("
                "email='migration-commerce@example.test', password='smoke-test-only'); "
                "order=place_order(actor=owner, currency='USD', "
                "lines=[{'sku': 'book', 'title': 'Book', "
                "'quantity': 1, 'unit_price_minor': 235}], "
                "idempotency_key='migration-commerce-order'); "
                "create_intent(actor=owner, amount_minor=235, currency='USD', "
                "source_order_id=order.pk, idempotency_key='migration-commerce-payment')",
            )
            run(
                "uv",
                "run",
                "python",
                "manage.py",
                "migrate",
                "--noinput",
                "--settings=config.settings.postgres_test",
            )
            run(
                "uv",
                "run",
                "python",
                "manage.py",
                "shell",
                "--settings=config.settings.postgres_test",
                "-c",
                "from apps.users.models import User; "
                "from apps.orders.models import Order, OrderItem; "
                "from apps.payments.models import PaymentIntent; "
                "owner=User.objects.get(email='migration-commerce@example.test'); "
                "order=Order.objects.get(owner=owner, "
                "idempotency_key='migration-commerce-order'); "
                "assert order.total_minor == 235 and order.status == 'placed'; "
                "assert OrderItem.objects.filter("
                "order=order, sku='BOOK', line_total_minor=235).count() == 1; "
                "assert PaymentIntent.objects.filter("
                "owner=owner, source_order_id=order.pk, amount_minor=235, "
                "status='pending', idempotency_key='migration-commerce-payment').count() == 1",
            )

        # Read-only migration ledger verification in the generated PostgreSQL client.
        # Detect missing, unexpected, partial or orphaned bundled revisions without
        # calling Django migrations or modifying any client schema.
        run(
            "uv",
            "run",
            "python",
            str(ROOT / "scripts" / "migration_adoption.py"),
            "--source",
            str(ROOT),
            "--project",
            str(target),
            "--verify-postgres",
            "--strict",
        )

        run(
            "uv",
            "run",
            "python",
            "manage.py",
            "makemigrations",
            "--check",
            "--dry-run",
            "--settings=config.settings.postgres_test",
        )
        run("uv", "run", "python", "manage.py", "check", "--settings=config.settings.postgres_test")
        run("uv", "run", "pytest", "-q", "--ds=config.settings.postgres_test")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=sorted(CASES), required=True)
    run_case(parser.parse_args().case)


if __name__ == "__main__":
    main()
