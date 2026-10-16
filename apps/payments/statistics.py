"""Payment metrics count only explicitly reconciled successful intents."""

from django.db.models import Sum

from apps.statistics.domain import Metric, Provider

from .models import PaymentIntent


def _pending(context):
    return PaymentIntent.objects.filter(owner=context.actor, status="pending").count()


def _succeeded(context):
    return PaymentIntent.objects.filter(
        owner=context.actor, status="succeeded", settled_at__gte=context.since,
        settled_at__lt=context.until,
    ).count()


def _collected(context):
    return (
        PaymentIntent.objects.filter(
            owner=context.actor, status="succeeded",
            settled_at__gte=context.since, settled_at__lt=context.until,
        ).aggregate(total=Sum("amount_minor"))["total"]
        or 0
    )


PROVIDER = Provider(
    code="payments",
    metrics=(
        Metric("pending", "Pending intents", "count", "snapshot", ("personal",), _pending),
        Metric("succeeded", "Reconciled successful intents", "count", "period",
               ("personal",), _succeeded),
        Metric("settled_minor", "Reconciled amount", "minor_units", "period",
               ("personal",), _collected),
    ),
)
