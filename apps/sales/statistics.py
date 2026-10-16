"""Sales aggregates count recorded facts, NOT captured payments."""

from django.db.models import Sum

from apps.statistics.domain import Metric, Provider

from .models import Sale


def _recorded(context):
    return Sale.objects.filter(owner=context.actor, status="recorded").count()


def _period_total(context):
    return (
        Sale.objects.filter(
            owner=context.actor,
            status="recorded",
            created_at__gte=context.since,
            created_at__lt=context.until,
        ).aggregate(total=Sum("total_minor"))["total"]
        or 0
    )


PROVIDER = Provider(
    code="sales",
    metrics=(
        Metric("recorded", "Recorded sales", "count", "snapshot", ("personal",), _recorded),
        Metric("period_total_minor", "Recorded value", "minor_units", "period",
               ("personal",), _period_total),
    ),
)
