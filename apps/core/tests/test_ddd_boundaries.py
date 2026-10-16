"""Architecture checks plus pure domain invariants for every implemented context."""

import ast
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest


APPS_ROOT = Path(__file__).resolve().parents[2]


def test_every_domain_is_framework_and_cross_context_independent():
    """Domain rules must remain usable without Django settings, DB or DRF."""
    contexts = {
        "users",
        "rbac",
        "organizations",
        "catalog",
        "inventory",
        "storage",
        "audit",
        "notifications",
    }
    for app_dir in APPS_ROOT.iterdir():
        domain = app_dir / "domain.py"
        if app_dir.name not in contexts or not domain.exists():
            continue
        tree = ast.parse(domain.read_text(encoding="utf-8"), filename=str(domain))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                continue
            assert not any(
                name == "apps"
                or name.startswith("apps.")
                or name == "django"
                or name.startswith("django.")
                or name == "rest_framework"
                or name.startswith("rest_framework.")
                for name in imported
            ), f"Framework or cross-context import in {domain}: {imported}"


def test_catalog_domain_enforces_attribute_constraints():
    pytest.importorskip("apps.catalog.domain")
    from apps.catalog.domain import CatalogRuleViolation, normalize_attributes, normalize_sku

    specs = [
        SimpleNamespace(code="weight", data_type="decimal", required=True),
        SimpleNamespace(code="count", data_type="integer", required=False),
        SimpleNamespace(code="gift", data_type="boolean", required=False),
    ]
    assert normalize_attributes(specs, {"weight": "2.50", "count": 3}) == {
        "weight": "2.50",
        "count": 3,
    }
    assert Decimal(normalize_attributes(specs, {"weight": "0.1"})["weight"]) == Decimal(
        "0.1"
    )
    with pytest.raises(CatalogRuleViolation):
        normalize_attributes(specs, {"count": 3})
    with pytest.raises(CatalogRuleViolation):
        normalize_attributes(specs, {"weight": "NaN"})
    with pytest.raises(CatalogRuleViolation):
        normalize_attributes(specs, {"weight": 2, "count": True})
    assert normalize_sku(" sku-12 ") == "SKU-12"


def test_inventory_domain_prevents_negative_and_over_reservation():
    pytest.importorskip("apps.inventory.domain")
    from apps.inventory.domain import (
        StockPosition,
        StockRuleViolation,
        require_open_reservation,
        validate_command_shape,
    )

    stock = StockPosition(on_hand=10, reserved=2)
    assert stock.available == 8
    assert stock.apply(physical=-8) == StockPosition(2, 2)
    assert stock.apply(held=3) == StockPosition(10, 5)
    for deltas in ({"physical": -9}, {"held": 9}, {"held": -3}):
        with pytest.raises(StockRuleViolation):
            stock.apply(**deltas)
    validate_command_shape("transfer", {"warehouse", "item", "quantity", "destination"})
    with pytest.raises(StockRuleViolation):
        validate_command_shape("transfer", {"warehouse", "item", "quantity"})
    with pytest.raises(StockRuleViolation):
        require_open_reservation("consumed")
    require_open_reservation("active")


def test_org_domain_preserves_last_owner_and_privileged_roles():
    pytest.importorskip("apps.organizations.domain")
    from apps.organizations.domain import may_manage_role, preserves_active_owner

    assert may_manage_role("owner", "owner", "member")
    assert may_manage_role("admin", "member", "manager")
    assert not may_manage_role("admin", "member", "owner")
    assert not may_manage_role("manager", "member")
    assert not preserves_active_owner(
        member_role="owner",
        member_active=True,
        next_role="member",
        deactivate=False,
        active_owner_count=1,
    )
    assert preserves_active_owner(
        member_role="owner",
        member_active=True,
        next_role="member",
        deactivate=True,
        active_owner_count=2,
    )


def test_audit_domain_rejects_credentials_and_bad_ids():
    pytest.importorskip("apps.audit.domain")
    from apps.audit.domain import sanitize_snapshot, validate_event_identity

    assert validate_event_identity("users.profile.updated", "users.User", 42) == "42"
    with pytest.raises(ValueError):
        validate_event_identity("!", "users.User", 42)
    assert sanitize_snapshot({"first_name": {"after": "A"}}) == {
        "first_name": {"after": "A"}
    }
    with pytest.raises(ValueError):
        sanitize_snapshot({"nested": {"api_key": "hidden"}})


def test_access_lifecycle_and_delivery_intents():
    from apps.users.domain import may_authenticate, may_send_verification
    from apps.notifications.domain import EmailIntent

    assert may_authenticate(active=True, verified=True)
    assert not may_authenticate(active=True, verified=False)
    assert may_send_verification(active=True, verified=False)
    intent = EmailIntent(
        recipient="a@example.test",
        subject="Hello",
        template="notifications/example.txt",
        context={},
    )
    with pytest.raises(FrozenInstanceError):
        intent.subject = "changed"


def test_storage_domain_ownership_policy():
    pytest.importorskip("apps.storage.domain")
    from apps.storage.domain import may_manage_file

    assert may_manage_file(actor_id=1, owner_id=1, elevated_in_scope=False)
    assert not may_manage_file(actor_id=1, owner_id=2, elevated_in_scope=False)


def test_rbac_domain_permission_policy():
    pytest.importorskip("apps.rbac.domain")
    from apps.rbac.domain import can_remove_role, parse_permission_code, unique_identifiers

    assert can_remove_role(assigned_user_count=0)
    assert not can_remove_role(assigned_user_count=1)
    assert parse_permission_code("users.change_user") == ("users", "change_user")
    assert parse_permission_code("bogus") is None
    assert unique_identifiers(["a", "b"])
    assert not unique_identifiers(["a", "a"])
