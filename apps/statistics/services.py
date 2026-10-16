"""Application layer: scope authorizations and date windows before any query."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.apps import apps
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from .domain import MetricsValidationError, resolve_period
from .registry import discover_metrics


@dataclass(frozen=True)
class MetricContext:
    actor: object
    scope: str
    period: object
    since: datetime
    until: datetime
    organization: object | None = None


def build_context(*, actor, scope, org_id=None, params=None):
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise NotFound()
    params = {} if params is None else params
    try:
        period = resolve_period(
            preset=params.get("period", "7d"),
            today=timezone.localdate(),
            start=params.get("start"),
            end=params.get("end"),
        )
    except MetricsValidationError as exc:
        raise ValidationError({"period": str(exc)}) from exc
    start = timezone.make_aware(datetime.combine(period.start_date, time.min))
    until = timezone.make_aware(datetime.combine(period.end_date + timedelta(days=1), time.min))
    organization = None
    if scope == "system":
        if not actor.is_superuser:
            raise PermissionDenied("System metrics require a superuser.")
    elif scope == "tenant":
        if not apps.is_installed("apps.organizations") or org_id is None:
            raise NotFound()
        from apps.organizations.models import Organization
        from apps.organizations.permissions import require_org_role

        organization = get_object_or_404(Organization, pk=org_id, is_active=True)
        require_org_role(
            user=actor,
            organization=organization,
            roles=("owner", "admin"),
        )
    elif scope != "personal":
        raise ValidationError({"scope": "Invalid statistics scope."})
    return MetricContext(
        actor=actor,
        scope=scope,
        period=period,
        since=start,
        until=until,
        organization=organization,
    )


def metric_definitions(context):
    return [
        {"key": key, "label": spec.label, "unit": spec.unit, "kind": spec.kind}
        for key, spec in discover_metrics(context.scope)
    ]


def metric_results(context):
    values = []
    for key, spec in discover_metrics(context.scope):
        value = spec.calculate(context)
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise MetricsValidationError(f"Metric {key} must return a numeric value.")
        if isinstance(value, Decimal):
            if not value.is_finite() or value != value.to_integral_value():
                raise MetricsValidationError(f"Metric {key} must be a finite integer.")
            value = int(value)
        values.append(
            {
                "key": key,
                "label": spec.label,
                "unit": spec.unit,
                "kind": spec.kind,
                "value": value,
            }
        )
    return values


def period_response(context):
    return {
        "name": context.period.name,
        "start": context.period.start_date.isoformat(),
        "end": context.period.end_date.isoformat(),
    }
