"""Correlation IDs and log serialization avoid URLs and payloads."""

import asyncio
import json
import logging

from django.http import HttpResponse
from django.test import RequestFactory

from apps.observability.context import current_request_id
from apps.observability.logging import JsonLogFormatter
from apps.observability.middleware import request_id_middleware


def test_sync_request_id_and_no_cross_request_leak(caplog):
    observed = []

    def downstream(_request):
        observed.append(current_request_id())
        return HttpResponse("ok")

    middleware = request_id_middleware(downstream)
    with caplog.at_level(logging.INFO, logger="apps.observability.http"):
        first = middleware(RequestFactory().get("/private/secret?token=private"))
        second = middleware(RequestFactory().get("/other"))
    assert first["X-Request-ID"] != second["X-Request-ID"]
    assert first["X-Request-ID"] == observed[0]
    assert current_request_id() is None
    assert "private" not in caplog.text
    assert "HTTP request completed" in caplog.text


def test_async_request_id_context_isolation():
    async def downstream(_request):
        assert current_request_id() is not None
        await asyncio.sleep(0)
        return HttpResponse("ok")

    async def scenario():
        middleware = request_id_middleware(downstream)
        first, second = await asyncio.gather(
            middleware(RequestFactory().get("/x")),
            middleware(RequestFactory().get("/y")),
        )
        assert first["X-Request-ID"] != second["X-Request-ID"]
        assert current_request_id() is None

    asyncio.run(scenario())


def test_json_formatter_only_emits_allowed_fields():
    record = logging.LogRecord(
        name="apps.example",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="done",
        args=(),
        exc_info=None,
    )
    record.request_id = "abcdef"
    record.method = "GET"
    record.route = "api/v1/listings/<uuid:pk>/"
    record.status = 200
    record.duration_ms = 1.25
    record.api_token = "do-not-log"
    content = JsonLogFormatter().format(record)
    data = json.loads(content)
    assert data["request_id"] == "abcdef"
    assert data["duration_ms"] == 1.25
    assert "api_token" not in content
    assert "do-not-log" not in content
