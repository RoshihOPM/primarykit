"""Run only when REDIS/RabbitMQ integration services are explicitly provisioned."""

import os

import pytest
from django.core.cache import caches
from django.test import override_settings

from apps.cache.config import build_cache_config
from apps.cache.services import get_cached, invalidate_cached, set_cached

pytestmark = pytest.mark.skipif(
    os.environ.get("PRIMARYKIT_INFRA_INTEGRATION") != "1",
    reason="Only run against explicitly provisioned Redis",
)


def test_real_redis_namespace_and_expiration():
    pytest.importorskip("redis")
    configuration = build_cache_config(
        enabled=True,
        url=os.environ["REDIS_CACHE_URL"],
        prefix="primarykit-ci-cache",
        timeout=30,
    )
    with override_settings(CACHES={"default": configuration}):
        assert caches["default"].set("healthcheck", "ok", timeout=20)
        assert caches["default"].get("healthcheck") == "ok"
        set_cached(namespace="client-a", key="same", value="A", timeout=30)
        assert get_cached(namespace="client-a", key="same") == "A"
        assert get_cached(namespace="client-b", key="same") is None
        invalidate_cached(namespace="client-a", key="same")
        assert get_cached(namespace="client-a", key="same") is None
        caches["default"].delete("healthcheck")
