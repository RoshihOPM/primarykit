"""Local, deploy-controlled feature flags; never use to make access decisions."""

import re
from collections.abc import Mapping

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def is_enabled(name: str) -> bool:
    """Return a strict boolean from the client-owned FEATURE_FLAGS mapping.

    Unknown flags default to False. Invalid configuration fails at use-time;
    no database, network, cache or global mutable state is involved.
    """
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError("Flag name must be snake_case, 1-64 characters")

    flags = getattr(settings, "FEATURE_FLAGS", {})
    if not isinstance(flags, Mapping):
        raise ImproperlyConfigured("FEATURE_FLAGS must be a mapping of string names to booleans")
    for key, value in flags.items():
        if not isinstance(key, str) or not _NAME.fullmatch(key) or type(value) is not bool:
            raise ImproperlyConfigured("FEATURE_FLAGS must contain valid names and bool values")
    return flags.get(name, False)
