"""Payment counts only. Cross-currency totals require currency grouping."""

from apps.statistics.domain import Metric, Provider

from .models import PaymentIntent


def _pending(context):
    return PaymentIntent.objects.filter(owner=context.actor, status="pending").count()


def _succeeded(context):
    return PaymentIntent.objects.filter(
        owner=context.actor,
        status="succeeded",
        settled_at__gte=context.since,
        settled_at__lt=context.until,
    ).count()


PROVIDER = Provider(
    code="payments",
    metrics=(
        Metric("pending", "Pending intents", "count", "snapshot", ("personal",), _pending),
        Metric("succeeded", "Reconciled successful intents", "count", "period",
               ("personal",), _succeeded),
    ),
)
