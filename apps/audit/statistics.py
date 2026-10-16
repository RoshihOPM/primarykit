"""Audit event count is security-sensitive and restricted to system superusers."""

from apps.statistics.domain import Metric, Provider

from .models import AuditEvent


def _events(context):
    return AuditEvent.objects.filter(
        occurred_at__gte=context.since, occurred_at__lt=context.until
    ).count()


PROVIDER = Provider(
    code="audit",
    metrics=(Metric("events", "Audit events", "count", "period", ("system",), _events),),
)
