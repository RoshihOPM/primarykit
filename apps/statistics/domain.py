"""Pure value objects for statistics; no business-module or Django imports."""

from dataclasses import dataclass
from datetime import date, timedelta


class MetricsValidationError(ValueError):
    """Invalid period or incompatible statistics contract."""


@dataclass(frozen=True)
class Period:
    start_date: date
    end_date: date
    name: str

    def __post_init__(self):
        if self.end_date < self.start_date:
            raise MetricsValidationError("End date cannot precede start date.")
        if (self.end_date - self.start_date).days > 365:
            raise MetricsValidationError("Date range cannot exceed 366 days.")


def resolve_period(*, preset: str, today: date, start: str | None, end: str | None) -> Period:
    if preset == "custom":
        if start is None or end is None:
            raise MetricsValidationError("Custom period requires start and end.")
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError as exc:
            raise MetricsValidationError("Dates must use YYYY-MM-DD.") from exc
        return Period(first, last, preset)
    if start is not None or end is not None:
        raise MetricsValidationError("Start and end are only allowed with period=custom.")
    sizes = {"today": 1, "7d": 7, "30d": 30}
    if preset not in sizes:
        raise MetricsValidationError("Period must be today, 7d, 30d or custom.")
    return Period(today - timedelta(days=sizes[preset] - 1), today, preset)


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str
    kind: str  # snapshot or period
    scopes: tuple[str, ...]
    calculate: object

    def __post_init__(self):
        if not self.key or self.kind not in ("snapshot", "period"):
            raise MetricsValidationError("Invalid metric definition.")
        if not self.scopes or not set(self.scopes) <= {"personal", "tenant", "system"}:
            raise MetricsValidationError("Invalid metric scopes.")
        if not callable(self.calculate):
            raise MetricsValidationError("Metric must provide a calculation function.")


@dataclass(frozen=True)
class Provider:
    code: str
    metrics: tuple[Metric, ...]

    def __post_init__(self):
        if not self.code or len({m.key for m in self.metrics}) != len(self.metrics):
            raise MetricsValidationError("Invalid metrics provider.")
