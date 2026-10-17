# HTTP Integrations — explicitly trusted outbound HTTPS

The optional `http_integrations` module is a synchronous adapter for
third-party provider calls. No public HTTP route, Django migration, Redis,
RabbitMQ or third-party Python dependency is installed.

Configure the transport **in server-owned code** with a hard-coded allowlist
of exact hostnames, and construct requests only with provider-relative paths:

```python
from apps.http_integrations.services import ProviderClient

provider = ProviderClient(
    base_url="https://api.example-provider.com/v1",
    allowed_hosts=("api.example-provider.com",),
    timeout=5.0,
    retries=2,
)
result = provider.request("GET", "/vehicles")
```

Host restrictions: HTTPS only, port 443, no URL credentials, fragment or query
in base origin, no localhost/local/internal hostnames or IP literals. The client
disables environment proxy handling, does **not follow redirects** and cannot
be given an absolute request URL. Path and response are bounded. Retries use
bounded exponential backoff on transport errors / 429 / 502 / 503 / 504, and
are limited to GET/HEAD/OPTIONS unless an explicit idempotency key is supplied.
POST/PUT/PATCH/DELETE without that key are never retried. Do not assume that
a remote provider implements an idempotency-key contract; verify with its API
docs before enabling retries for its non-safe methods.

Security notes: DNS rebinding and private-IP DNS resolution require **network
egress restrictions and controlled provider DNS** at deployment; a hostname
allowlist alone does not supply complete SSRF protection. Provider credentials
should come from a trusted secrets manager, not client input. Never log URL
queries, credentials, payloads, response bodies or raw transport exceptions.
`ProviderTransportError` deliberately returns a generic message.

This is a small synchronous foundation. Client services own retry budgets,
remote provider data validation, distributed circuit breaking, metrics,
monitoring and sandbox integration tests. It is not a payment gateway and
does not guarantee exactly-once delivery.
