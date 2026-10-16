"""Order-owning context exposes personal, idempotency-safe metrics."""

from apps.statistics.domain import Metric, Provider

from .models import Order


def _total(context):
    return Order.objects.filter(owner=context.actor).count()


def _placed(context):
    return Order.objects.filter(owner=context.actor, status="placed").count()


def _new(context):
    return Order.objects.filter(
        owner=context.actor, created_at__gte=context.since, created_at__lt=context.until
    ).count()


PROVIDER = Provider(
    code="orders",
    metrics=(
        Metric("total", "Orders", "count", "snapshot", ("personal",), _total),
        Metric("placed", "Placed orders", "count", "snapshot", ("personal",), _placed),
        Metric("new", "New orders", "count", "period", ("personal",), _new),
    ),
)
