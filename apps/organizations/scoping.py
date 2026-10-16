"""Shared tenant-boundary helpers for modules copied alongside Organizations."""

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, PermissionDenied

from .models import BranchAccess, Membership, Organization
from .permissions import get_active_membership

WRITERS = (Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGER)
FULL_ACCESS = (Membership.Role.OWNER, Membership.Role.ADMIN)


def organization_scope(*, user, org_id):
    organization = get_object_or_404(Organization, pk=org_id, is_active=True)
    return organization, get_active_membership(user=user, organization=organization)


def require_writer(membership):
    if membership.role not in WRITERS:
        raise PermissionDenied("Membership does not permit writes.")


def branch_ids_for(membership):
    return BranchAccess.objects.filter(
        membership=membership,
        branch__is_active=True,
        branch__organization_id=membership.organization_id,
    ).values_list("branch_id", flat=True)


def require_warehouse_access(*, membership, warehouse, writing=False):
    if warehouse.organization_id != membership.organization_id:
        raise NotFound()
    if not warehouse.is_active or not warehouse.branch.is_active:
        raise NotFound()
    if writing:
        require_writer(membership)
    if membership.role not in FULL_ACCESS and not BranchAccess.objects.filter(
        membership=membership, branch_id=warehouse.branch_id,
        branch__organization_id=membership.organization_id,
        branch__is_active=True,
    ).exists():
        raise NotFound()
