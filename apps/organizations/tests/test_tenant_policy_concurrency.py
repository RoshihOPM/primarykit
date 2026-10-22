"""PostgreSQL transaction races: ownership and branch grants are authoritative."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from django.db import close_old_connections, connection, connections, transaction
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.organizations.models import Branch, BranchAccess, Membership, Organization
from apps.organizations.policy import TenantPolicy
from apps.organizations.services import set_branch_access, update_membership
from apps.users.models import User


def make_user(email):
    return User.objects.create_user(
        email=email, password="long-test-password-123", email_verified=True
    )


@pytest.mark.django_db(transaction=True)
def test_owner_demotion_commits_before_locked_writer_authorization():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    org = Organization.objects.create(slug="policy-role-race", name="Role race")
    actor = make_user("role-actor@policy.test")
    other_owner = make_user("role-other@policy.test")
    member = Membership.objects.create(organization=org, user=actor, role=Membership.Role.OWNER)
    Membership.objects.create(organization=org, user=other_owner, role=Membership.Role.OWNER)
    changed, attempting, release = Event(), Event(), Event()

    def downgrade():
        close_old_connections()
        try:
            with transaction.atomic():
                update_membership(
                    actor=other_owner,
                    organization=org,
                    membership_id=member.pk,
                    new_role=Membership.Role.MEMBER,
                )
                changed.set()
                assert release.wait(timeout=10)
        finally:
            connections.close_all()

    def attempt_write():
        close_old_connections()
        try:
            attempting.set()
            try:
                with transaction.atomic():
                    policy = TenantPolicy.resolve(user=actor, organization_id=org.pk, lock=True)
                    policy.require_write()
            except PermissionDenied:
                return "denied"
            return "allowed"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        change = pool.submit(downgrade)
        try:
            assert changed.wait(timeout=10)
            command = pool.submit(attempt_write)
            assert attempting.wait(timeout=10)
        finally:
            release.set()
        change.result(timeout=15)
        assert command.result(timeout=15) == "denied"
    member.refresh_from_db()
    assert member.role == Membership.Role.MEMBER


@pytest.mark.django_db(transaction=True)
def test_branch_revocation_commits_before_locked_branch_authorization():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    org = Organization.objects.create(slug="policy-branch-race", name="Branch race")
    owner = make_user("branch-owner@policy.test")
    manager = make_user("branch-manager@policy.test")
    Membership.objects.create(organization=org, user=owner, role=Membership.Role.OWNER)
    membership = Membership.objects.create(
        organization=org, user=manager, role=Membership.Role.MANAGER
    )
    branch = Branch.objects.create(organization=org, code="main", name="Main")
    BranchAccess.objects.create(membership=membership, branch=branch)
    changed, attempting, release = Event(), Event(), Event()

    def revoke():
        close_old_connections()
        try:
            with transaction.atomic():
                set_branch_access(
                    actor=owner,
                    organization=org,
                    membership_id=membership.pk,
                    branch_ids=[],
                )
                changed.set()
                assert release.wait(timeout=10)
        finally:
            connections.close_all()

    def attempt_branch_command():
        close_old_connections()
        try:
            attempting.set()
            try:
                with transaction.atomic():
                    policy = TenantPolicy.resolve(user=manager, organization_id=org.pk, lock=True)
                    policy.require_write()
                    policy.require_branch(branch=branch)
            except NotFound:
                return "denied"
            return "allowed"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        change = pool.submit(revoke)
        try:
            assert changed.wait(timeout=10)
            command = pool.submit(attempt_branch_command)
            assert attempting.wait(timeout=10)
        finally:
            release.set()
        change.result(timeout=15)
        assert command.result(timeout=15) == "denied"
    assert not BranchAccess.objects.filter(membership=membership).exists()
