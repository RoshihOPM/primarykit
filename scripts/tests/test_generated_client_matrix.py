"""Smoke-matrix configuration tests without live database dependencies."""

import pytest

from scripts.ci_generated_client import CASES, run_case


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
