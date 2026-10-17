"""Server-generated request IDs and structured request metrics, with no PII."""

import logging
import time
import uuid

from asgiref.sync import iscoroutinefunction
from django.utils.decorators import sync_and_async_middleware
from django.utils.functional import lazy

from apps.observability.context import request_id_var

logger = logging.getLogger("apps.observability.http")


def _record(request, response, started, request_id):
    route_match = getattr(request, "resolver_match", None)
    route = getattr(route_match, "route", None) or "unmatched"
    logger.info(
        "HTTP request completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "route": route,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    response["X-Request-ID"] = request_id
    return response


@sync_and_async_middleware
def request_id_middleware(get_response):
    """Do not accept untrusted inbound IDs, prevent cross-request context leakage."""
    if iscoroutinefunction(get_response):

        async def middleware(request):
            request_id = uuid.uuid4().hex
            token = request_id_var.set(request_id)
            started = time.perf_counter()
            try:
                response = await get_response(request)
                return _record(request, response, started, request_id)
            finally:
                request_id_var.reset(token)

        return middleware

    def middleware(request):
        request_id = uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = get_response(request)
            return _record(request, response, started, request_id)
        finally:
            request_id_var.reset(token)

    return middleware
