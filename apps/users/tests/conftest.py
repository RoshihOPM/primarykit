import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def isolate_auth_throttling():
    """Prevent rate-limiter state leaking across independent API tests."""
    cache.clear()
    yield
    cache.clear()
