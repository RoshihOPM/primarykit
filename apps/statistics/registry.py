"""Optional metric providers are defined and owned inside each copied app."""

from importlib import import_module
from importlib.util import find_spec

from django.apps import apps

from .domain import MetricsValidationError, Provider


def discover_metrics(scope: str):
    """Import only installed providers. Fail on duplicates; never silently downgrade scope."""
    metrics = []
    used = set()
    for app in apps.get_app_configs():
        if not app.name.startswith("apps.") or app.label == "statistics":
            continue
        module_path = f"{app.name}.statistics"
        if find_spec(module_path) is None:
            continue
        provider = getattr(import_module(module_path), "PROVIDER", None)
        if not isinstance(provider, Provider) or provider.code != app.label:
            raise MetricsValidationError(f"Invalid metric provider: {app.label}")
        for metric in provider.metrics:
            if scope not in metric.scopes:
                continue
            key = f"{provider.code}.{metric.key}"
            if key in used:
                raise MetricsValidationError(f"Duplicate metric key: {key}")
            used.add(key)
            metrics.append((key, metric))
    return tuple(sorted(metrics, key=lambda pair: pair[0]))
