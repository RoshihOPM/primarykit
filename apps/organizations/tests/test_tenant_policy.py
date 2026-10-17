"""Negative tenant policy tests independent of Catalog/Inventory schema modes."""

import uuid

import pytest
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.organizations.models import Branch, BranchAccess, Membership, Organization
from apps.organizations.policy import TenantPolicy
from apps.users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenants():
    first = Organization.objects.create(slug="policy-first", name="First")
    second = Organization.objects.create(slug="policy-second", name="Second")
    writer = User.objects.create_user(
        email="policy-writer@example.test",
        password="long-test-password-100",
        email_verified=True,
    )
    outsider = User.objects.create_user(
        email="policy-outsider@example.test",
        password="long-test-password-200",
        email_verified=True,
        is_staff=True,
        is_superuser=True,
    )
    membership = Membership.objects.create(
        organization=first, user=writer, role=Membership.Role.MANAGER
    )
    first_branch = Branch.objects.create(
        organization=first, code="first", name="First branch"
    )
    other_branch = Branch.objects.create(
        organization=first, code="other", name="Other branch"
    )
    foreign_branch = Branch.objects.create(
        organization=second, code="foreign", name="Foreign branch"
    )
    BranchAccess.objects.create(membership=membership, branch=first_branch)
    return locals()


@pytest.mark.parametrize("invalid", [None, "", "not-a-uuid", 5])
def test_absent_and_invalid_organizations_fail_closed(tenants, invalid):
    with pytest.raises(NotFound):
        TenantPolicy.resolve(user=tenants["writer"], organization_id=invalid)
    with pytest.raises(NotFound):
        TenantPolicy.resolve(user=tenants["writer"], organization_id=uuid.uuid4())


def test_authentication_and_global_superuser_do_not_bypass_membership(tenants):
    org = tenants["first"]
    with pytest.raises(NotFound):
        TenantPolicy.resolve(user=AnonymousUser(), organization_id=org.pk)
    with pytest.raises(NotFound):
        TenantPolicy.resolve(user=tenants["outsider"], organization_id=org.pk)


def test_disabled_user_membership_and_organization_fail_closed(tenants):
    actor = tenants["writer"]
    membership = tenants["membership"]
    org = tenants["first"]
    actor.is_active = False
    actor.save(update_fields=["is_active"])
    with pytest.raises(NotFound):
        TenantPolicy.resolve(user=actor, organization_id=org.pk)
    actor.is_active = True
    actor.save(update_fields=["is_active"])
    membership.is_active = False
    membership.save(update_fields=["is_active"])
    with pytest.raises(NotFound):
        TenantPolicy.resolve(user=actor, organization_id=org.pk)
    membership.is_active = True
    membership.save(update_fields=["is_active"])
    org.is_active = False
    org.save(update_fields=["is_active"])
    with pytest.raises(NotFound):
        TenantPolicy.resolve(user=actor, organization_id=org.pk)


def test_policy_scopes_list_detail_and_requires_explicit_organization_field(tenants):
    policy = TenantPolicy.resolve(
        user=tenants["writer"], organization_id=tenants["first"].pk
    )
    queryset = policy.scope_queryset(
        Branch.objects.all(), organization_field="organization"
    )
    assert set(queryset.values_list("pk", flat=True)) == {
        tenants["first_branch"].pk,
        tenants["other_branch"].pk,
    }
    assert not queryset.filter(pk=tenants["foreign_branch"].pk).exists()
    with pytest.raises(ValueError):
        policy.scope_queryset(Branch.objects.all(), organization_field="")


def test_branch_list_and_detail_require_grant_and_matching_tenant(tenants):
    policy = TenantPolicy.resolve(
        user=tenants["writer"], organization_id=tenants["first"].pk
    )
    granted = tenants["first_branch"]
    ungranted = tenants["other_branch"]
    foreign = tenants["foreign_branch"]
    policy.require_branch(branch=granted)
    for branch in (ungranted, foreign):
        with pytest.raises(NotFound):
            policy.require_branch(branch=branch)
    # Broken raw ORM grant must never confer cross-tenant branch access.
    BranchAccess.objects.create(membership=tenants["membership"], branch=foreign)
    with pytest.raises(NotFound):
        policy.require_branch(branch=foreign)
    grants = policy.scope_queryset(
        BranchAccess.objects.all(),
        organization_field="branch__organization",
        branch_field="branch",
    )
    assert set(grants.values_list("branch_id", flat=True)) == {granted.pk}


def test_inactive_branch_and_revoked_grant_are_not_accessible(tenants):
    policy = TenantPolicy.resolve(
        user=tenants["writer"], organization_id=tenants["first"].pk
    )
    branch = tenants["first_branch"]
    branch.is_active = False
    branch.save(update_fields=["is_active"])
    with pytest.raises(NotFound):
        policy.require_branch(branch=branch)
    assert not policy.scope_queryset(
        BranchAccess.objects.all(),
        organization_field="branch__organization",
        branch_field="branch",
    ).exists()
    branch.is_active = True
    branch.save(update_fields=["is_active"])
    BranchAccess.objects.filter(membership=tenants["membership"]).delete()
    with pytest.raises(NotFound):
        policy.require_branch(branch=branch)


def test_members_cannot_write_and_owners_can_read_any_branch(tenants):
    membership = tenants["membership"]
    policy = TenantPolicy.resolve(
        user=tenants["writer"], organization_id=tenants["first"].pk
    )
    policy.require_write()
    membership.role = Membership.Role.MEMBER
    membership.save(update_fields=["role"])
    with pytest.raises(PermissionDenied):
        TenantPolicy.resolve(
            user=tenants["writer"], organization_id=tenants["first"].pk
        ).require_write()
    membership.role = Membership.Role.OWNER
    membership.save(update_fields=["role"])
    policy = TenantPolicy.resolve(
        user=tenants["writer"], organization_id=tenants["first"].pk
    )
    policy.require_branch(branch=tenants["other_branch"])
    with pytest.raises(NotFound):
        policy.require_branch(branch=tenants["foreign_branch"])


def test_locked_scope_requires_transaction_and_rechecks_active_membership(tenants):
    actor = tenants["writer"]
    org = tenants["first"]
    with pytest.raises(RuntimeError):
        TenantPolicy.resolve(user=actor, organization_id=org.pk, lock=True)
    with transaction.atomic():
        policy = TenantPolicy.resolve(user=actor, organization_id=org.pk, lock=True)
        assert policy.organization == org
        assert policy.membership == tenants["membership"]
