"""Backwards-compatible helpers backed by the shared Organizations policy."""

from rest_framework.exceptions import NotFound

from .policy import FULL_ACCESS as FULL_ACCESS
from .policy import WRITERS as WRITERS
from .policy import TenantPolicy


def organization_scope(*, user, org_id):
    policy = TenantPolicy.resolve(user=user, organization_id=org_id)
    return policy.organization, policy.membership


def require_writer(membership):
    TenantPolicy(organization=membership.organization, membership=membership).require_write()


def branch_ids_for(membership):
    return TenantPolicy(organization=membership.organization, membership=membership).branch_ids()


def require_warehouse_access(*, membership, warehouse, writing=False):
    policy = TenantPolicy(organization=membership.organization, membership=membership)
    policy.require_organization(warehouse.organization_id)
    if not warehouse.is_active:
        raise NotFound()
    if writing:
        policy.require_write()
    policy.require_branch(branch=warehouse.branch)
