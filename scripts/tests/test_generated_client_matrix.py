"""Smoke-matrix configuration tests without live database dependencies."""

import pytest

from scripts.ci_generated_client import CASES, run_case
from scripts.new_project import project_plan


def test_matrix_compositions():
    assert {
        "minimal",
        "crm",
        "marketplace",
        "commerce",
        "api_keys",
        "tasks",
        "webhooks",
        "all",
    } <= set(CASES)


def test_reject_unknown_case():
    with pytest.raises(ValueError, match="Unknown matrix case"):
        run_case("missing")


def test_postgresql_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        run_case("minimal")


@pytest.mark.parametrize(
    ("case", "has_commerce"),
    [("minimal", False), ("commerce", True), ("all", True)],
)
def test_migration_smoke_matrix_contains_expected_commerce_modules(case, has_commerce):
    options = CASES[case]
    plan = project_plan(
        requested_apps=set(options.get("apps", ())),
        preset=options.get("preset"),
    )
    assert ({"orders", "payments"} <= set(plan["included_apps"])) is has_commerce
