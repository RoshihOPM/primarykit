"""Tenant-only company indicators; Statistics service enforces owner/admin membership."""

from apps.statistics.domain import Metric, Provider

from .models import Branch, Membership


def _members(context):
    return Membership.objects.filter(organization=context.organization, is_active=True).count()


def _branches(context):
    return Branch.objects.filter(organization=context.organization, is_active=True).count()


PROVIDER = Provider(
    code="organizations",
    metrics=(
        Metric("members", "Active memberships", "count", "snapshot", ("tenant",), _members),
        Metric("branches", "Active branches", "count", "snapshot", ("tenant",), _branches),
    ),
)
