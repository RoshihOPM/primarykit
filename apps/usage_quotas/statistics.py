"""Opt-in statistics integration. The metrics service authorizes the context."""

from django.db.models import Q, Sum
from django.utils import timezone

from apps.statistics.domain import Metric, Provider

from .models import UsageEvent, UsagePolicy


def _policies(context):
    now = timezone.now()
    base = UsagePolicy.objects.filter(period_start__lte=now, period_end__gt=now)
    if context.scope == "personal":
        base = base.filter(scope="owner", owner=context.actor)
    elif context.scope == "tenant":
        base = base.filter(scope="tenant", tenant_id=context.organization.pk)
    else:
        return 0
    return base.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).count()


def _consumed(context):
    events = UsageEvent.objects.filter(created_at__gte=context.since, created_at__lt=context.until)
    if context.scope == "personal":
        events = events.filter(policy__scope="owner", policy__owner=context.actor)
    elif context.scope == "tenant":
        events = events.filter(policy__scope="tenant", policy__tenant_id=context.organization.pk)
    else:
        return 0
    return events.aggregate(total=Sum("units"))["total"] or 0


PROVIDER = Provider(
    code="usage_quotas",
    metrics=(
        Metric(
            "active_policies",
            "Active usage policies",
            "count",
            "snapshot",
            ("personal", "tenant"),
            _policies,
        ),
        Metric(
            "consumed_units", "Consumed units", "units", "period", ("personal", "tenant"), _consumed
        ),
    ),
)
