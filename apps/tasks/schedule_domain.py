"""Pure recurring schedule validation and wall-clock/DST rules."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.tasks.domain import require_aware_datetime


def validate_calendar(*, timezone_name: str, hour: int, minute: int, weekdays=None):
    """Weekdays are Python weekdays (Monday=0); an empty set means every day."""
    if not isinstance(timezone_name, str) or not 1 <= len(timezone_name) <= 64:
        raise ValueError("Invalid schedule timezone")
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError("Unknown schedule timezone") from exc
    if type(hour) is not int or not 0 <= hour <= 23:
        raise ValueError("Schedule hour must be from 0 to 23")
    if type(minute) is not int or not 0 <= minute <= 59:
        raise ValueError("Schedule minute must be from 0 to 59")
    if weekdays is None:
        weekdays = []
    if not isinstance(weekdays, (list, tuple)) or any(
        type(day) is not int or not 0 <= day <= 6 for day in weekdays
    ):
        raise ValueError("Schedule weekdays must be integers from 0 to 6")
    if len(set(weekdays)) != len(weekdays):
        raise ValueError("Schedule weekdays must be unique")
    return sorted(weekdays)


def next_fire_after(
    *,
    after: datetime,
    timezone_name: str,
    hour: int,
    minute: int,
    weekdays=(),
) -> datetime:
    """Find the first eligible UTC instant strictly after `after`.

    A DST gap is skipped, not shifted to a different wall time. In a DST fold,
    the first occurrence (fold=0) is used, and the second is never fired.
    """
    require_aware_datetime(after)
    days = validate_calendar(
        timezone_name=timezone_name, hour=hour, minute=minute, weekdays=weekdays
    )
    zone = ZoneInfo(timezone_name)
    utc_after = after.astimezone(UTC)
    start = after.astimezone(zone).date()

    # 15 days covers a weekly run skipped by a spring DST gap.
    for offset in range(15):
        day = start + timedelta(days=offset)
        if days and day.weekday() not in days:
            continue
        wall = datetime.combine(day, time(hour, minute))
        instant = wall.replace(tzinfo=zone, fold=0).astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) != wall:
            continue  # Local wall-clock time does not exist (DST spring gap).
        if instant > utc_after:
            return instant
    raise ValueError("No next schedule occurrence in the supported calendar window")
