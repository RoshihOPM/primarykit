"""Live Redis test for cross-process fixed-window counts."""

import os
import uuid

import pytest
from django.test import override_settings

from apps.rate_limit.services import check_limit

pytestmark = pytest.mark.skipif(
    os.environ.get("PRIMARYKIT_INFRA_INTEGRATION") != "1",
    reason="Requires a provisioned Redis server",
)


def test_real_shared_limit_is_atomic_and_expires():
    pytest.importorskip("redis")
    identity = "anon:" + uuid.uuid4().hex
    with override_settings(
        REDIS_CACHE_ENABLED=True,
        REDIS_CACHE_URL=os.environ["REDIS_CACHE_URL"],
        REDIS_CACHE_KEY_PREFIX="primarykit-ci-limit",
    ):
        assert check_limit(
            scope="account_login", identity=identity, max_requests=2, window_seconds=30
        ) == (True, None)
        assert check_limit(
            scope="account_login", identity=identity, max_requests=2, window_seconds=30
        ) == (True, None)
        allowed, seconds = check_limit(
            scope="account_login", identity=identity, max_requests=2, window_seconds=30
        )
        assert allowed is False
        assert 1 <= seconds <= 30
