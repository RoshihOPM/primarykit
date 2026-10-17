"""Explicit, reusable tenant authorization adapter for copied business modules.

Organizations Membership and BranchAccess remain the *only* authorities for
tenant roles and branch grants. The caller must opt into scoping for every
queryset and resolve a fresh locked policy inside a transaction for commands.
"""

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied

from .models import BranchAccess, Membership, Organization
from .permissions import get_active_membership

WRITERS = frozenset({Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGER})
FULL_ACCESS = frozenset({Membership.Role.OWNER, Membership.Role.ADMIN})


@dataclass(frozen=True)
class TenantPolicy:
    organization: Organization
    membership: Membership

    @classmethod
    def resolve(cls, *, user, organization_id, lock=False):
        """404 for missing/inactive/unrelated tenants, including for superusers.

        With lock=True, lock the Organization row *before* reading membership.
        Organization membership and branch-grant commands take the same row lock.
        A calling service must already be inside transaction.atomic().
        """
        if lock and not transaction.get_connection().in_atomic_block:
            raise RuntimeError("A locked tenant policy requires transaction.atomic().")
        try:
            organization_id = UUID(str(organization_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise NotFound() from exc

        organizations = Organization.objects.filter(pk=organization_id, is_active=True)
        if lock:
            organizations = organizations.select_for_update()
        organization = organizations.first()
        if organization is None:
            raise NotFound()
        membership = get_active_membership(user=user, organization=organization)
        return cls(organization=organization, membership=membership)

    @property
    def has_full_access(self):
        return self.membership.role in FULL_ACCESS

    def require_roles(self, roles):
        if self.membership.role not in roles:
            raise PermissionDenied("Insufficient organization privileges.")

    def require_write(self):
        self.require_roles(WRITERS)

    def require_organization(self, organization_id):
        if self.organization.pk != organization_id:
            raise NotFound()

    def branch_ids(self, *, active_only=True):
        grants = BranchAccess.objects.filter(
            membership=self.membership,
            branch__organization=self.organization,
        )
        if active_only:
            grants = grants.filter(branch__is_active=True)
        return grants.values_list("branch_id", flat=True)

    def require_branch(self, *, branch, active_only=True):
        self.require_organization(branch.organization_id)
        if active_only and not branch.is_active:
            raise NotFound()
        if self.has_full_access:
            return
        if not BranchAccess.objects.filter(
            membership=self.membership,
            branch=branch,
            branch__organization=self.organization,
            **({"branch__is_active": True} if active_only else {}),
        ).exists():
            raise NotFound()

    def scope_queryset(
        self,
        queryset,
        *,
        organization_field,
        branch_field=None,
        active_branches=True,
    ):
        """Scope list AND detail base querysets; field paths are trusted constants.

        The caller may add stricter business visibility filters, never replace
        this boundary. For branch resources, both tenant and grant must match.
        """
        if not organization_field:
            raise ValueError("An explicit organization field is required.")
        scoped = queryset.filter(**{organization_field: self.organization})
        if branch_field is None:
            return scoped
        scoped = scoped.filter(**{f"{branch_field}__organization": self.organization})
        if active_branches:
            scoped = scoped.filter(**{f"{branch_field}__is_active": True})
        if not self.has_full_access:
            scoped = scoped.filter(
                **{f"{branch_field}__pk__in": self.branch_ids(active_only=active_branches)}
            )
        return scoped
