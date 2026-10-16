"""System-wide account metrics; never exposed on personal or tenant endpoints."""

from apps.statistics.domain import Metric, Provider

from .models import User


def _total(_context):
    return User.objects.count()


def _active(_context):
    return User.objects.filter(is_active=True).count()


def _registered(context):
    return User.objects.filter(date_joined__gte=context.since, date_joined__lt=context.until).count()


PROVIDER = Provider(
    code="users",
    metrics=(
        Metric("total_users", "Registered users", "count", "snapshot", ("system",), _total),
        Metric("active_users", "Active users", "count", "snapshot", ("system",), _active),
        Metric("new_users", "New registrations", "count", "period", ("system",), _registered),
    ),
)
