"""Storage access port: standalone owner policy or optional Organizations adapter.

The Storage domain only persists a nullable organization UUID, never a
cross-context ORM relationship. Tenant membership is resolved at the boundary.
"""

from dataclasses import dataclass
from uuid import UUID

from django.apps import apps as django_apps
from rest_framework.exceptions import NotFound

from .domain import may_manage_file


@dataclass(frozen=True)
class FileScope:
    organization_id: UUID | None
    can_manage_all: bool = False


def resolve_file_scope(*, user, organization_id=None, lock=False) -> FileScope:
    """Fail closed: no implicit superuser or staff tenant access."""
    if not user or not user.is_authenticated or not user.is_active:
        raise NotFound()
    if organization_id is None:
        return FileScope(organization_id=None)

    if not django_apps.is_installed("apps.organizations"):
        raise NotFound()

    # Optional adapter imports belong at the boundary, never in models/services.
    from apps.organizations.policy import TenantPolicy

    policy = TenantPolicy.resolve(user=user, organization_id=organization_id, lock=lock)
    return FileScope(
        organization_id=policy.organization.pk,
        can_manage_all=policy.has_full_access,
    )


def visible_files(*, queryset, user, scope: FileScope):
    queryset = queryset.filter(organization_id=scope.organization_id)
    if scope.can_manage_all:
        return queryset
    return queryset.filter(owner=user)


def require_file_access(*, file, actor, scope: FileScope):
    if file.organization_id != scope.organization_id:
        raise NotFound()
    if not may_manage_file(
        actor_id=actor.pk,
        owner_id=file.owner_id,
        elevated_in_scope=scope.can_manage_all,
    ):
        raise NotFound()
