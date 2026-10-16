"""Sales counts only. Cross-currency monetary totals require currency grouping."""

from apps.statistics.domain import Metric, Provider

from .models import Sale


def _recorded(context):
    return Sale.objects.filter(owner=context.actor, status="recorded").count()


def _new(context):
    return Sale.objects.filter(
        owner=context.actor,
        status="recorded",
        created_at__gte=context.since,
        created_at__lt=context.until,
    ).count()


PROVIDER = Provider(
    code="sales",
    metrics=(
        Metric("recorded", "Recorded sales", "count", "snapshot", ("personal",), _recorded),
        Metric("period_recorded", "New recorded sales", "count", "period", ("personal",), _new),
    ),
)
