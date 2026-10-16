"""Private object metadata metrics. Never reads S3 or exposes object keys."""

from django.db.models import Sum

from apps.statistics.domain import Metric, Provider

from .models import StoredFile


def _scope(context):
    if context.scope == "tenant":
        return {"organization_id": context.organization.pk}
    return {"organization_id__isnull": True, "owner": context.actor}


def _files(context):
    return StoredFile.objects.filter(**_scope(context), deleted_at__isnull=True)


def _count(context):
    return _files(context).count()


def _bytes(context):
    return _files(context).aggregate(value=Sum("size"))["value"] or 0


def _uploads(context):
    return _files(context).filter(
        created_at__gte=context.since, created_at__lt=context.until
    ).count()


PROVIDER = Provider(
    code="storage",
    metrics=(
        Metric("files", "Active files", "count", "snapshot", ("personal", "tenant"), _count),
        Metric("bytes", "Stored bytes", "bytes", "snapshot", ("personal", "tenant"), _bytes),
        Metric("uploads", "New active uploads", "count", "period", ("personal", "tenant"), _uploads),
    ),
)
