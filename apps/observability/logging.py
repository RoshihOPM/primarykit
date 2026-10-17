"""JSON log format without external logging dependencies."""

import json
from datetime import UTC, datetime
from logging import Formatter

from apps.observability.context import current_request_id


class JsonLogFormatter(Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation = getattr(record, "request_id", None) or current_request_id()
        if correlation:
            payload["request_id"] = correlation
        for key in ("method", "route", "status", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        # Deliberately omit exception text, query strings, request/response bodies.
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
