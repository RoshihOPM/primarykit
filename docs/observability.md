# Observability: request IDs and JSON logs

`--apps observability` adds a **standalone** observability adapter to a generated Django backend. It uses the standard library plus Django/asgiref; no Prometheus, Sentry or external managed service is required for basic operation.

When selected, middleware generates a random request ID per HTTP request, exposes it as `X-Request-ID` and records method, **normalized URL route** (not path/query values), status and duration in milliseconds. ContextVar isolates request ID across sync and async requests, and is reset after processing.

Production logs are JSON objects with timestamp, level, logger, request_id and optional method/route/status/duration_ms. Log handlers must **not** include request bodies, auth headers, tokens, query strings or exception text: the adapter deliberately doesn't add them. External logs emitted by client code may still contain sensitive data; review business log statements.

```bash
uv run python scripts/new_project.py ../backend --name backend --apps observability
cd ../backend
python -m apps.core.doctor --strict
```

The module does not add database tables or migrations. Each generated client can add its own OpenTelemetry SDK or error-reporting integration later; no automatic dependency on upstream PrimaryKit.

For production readiness, feed JSON logs into an aggregator, alert on 5xx/error rates, queue age and task failures, and test backup restores. Redis/RabbitMQ readiness probes require enabling and operating those services explicitly; never turn optional brokers into mandatory Django imports.
