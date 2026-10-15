"""Explicit tenant-membership checks. Never use global Django Group as tenant role."""

from rest_framework.exceptions import NotFound, PermissionDenied

from .models import BranchAccess, Membership


def get_active_membership(*, user, organization):
    if not user or not user.is_authenticated or not user.is_active or not organization.is_active:
        raise NotFound()
    membership = Membership.objects.filter(
        user=user, organization=organization, is_active=True
    ).first()
    if membership is None:
        raise NotFound()
    return membership


def require_org_role(*, user, organization, roles):
    membership = get_active_membership(user=user, organization=organization)
    if membership.role not in roles:
        raise PermissionDenied("Insufficient organization privileges.")
    return membership


def require_branch_access(*, user, branch):
    membership = get_active_membership(user=user, organization=branch.organization)
    if not branch.is_active:
        raise NotFound()
    if membership.role in {Membership.Role.OWNER, Membership.Role.ADMIN}:
        return membership
    if not BranchAccess.objects.filter(membership=membership, branch=branch).exists():
        raise NotFound()
    return membership
