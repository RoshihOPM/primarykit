"""Bounded outbound HTTPS for provider integrations, with no arbitrary URL fetching."""

import http.client
import ipaddress
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

_MAX_REQUEST = 65536
_MAX_RESPONSE = 1048576
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_RETRYABLE = frozenset({429, 502, 503, 504})
_KEY = re.compile(r"^[A-Za-z0-9:_-]{1,128}$")


class ProviderTransportError(RuntimeError):
    """External provider unreachable or response size exceeded."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _open(request, timeout):
    # No environment HTTP_PROXY use; no redirect to unexpected hosts.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    return opener.open(request, timeout=timeout)


@dataclass(frozen=True)
class ProviderResponse:
    status: int
    body: bytes

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class ProviderClient:
    """Configure in trusted server code; never take hosts from request inputs."""

    def __init__(
        self,
        *,
        base_url: str,
        allowed_hosts: tuple[str, ...],
        timeout: float = 5.0,
        retries: int = 2,
        max_response_bytes: int = _MAX_RESPONSE,
    ):
        if not isinstance(base_url, str) or not isinstance(allowed_hosts, tuple):
            raise ValueError("Supply a trusted HTTPS origin and a hostname allowlist")
        parsed = urllib.parse.urlsplit(base_url)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.port not in (None, 443)
            or host not in allowed_hosts
            or host == "localhost"
            or host.endswith((".localhost", ".local", ".internal"))
        ):
            raise ValueError("Provider origin must be an explicitly permitted HTTPS hostname")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("IP-literal provider URLs are not supported")
        if (
            not isinstance(timeout, (int, float))
            or isinstance(timeout, bool)
            or not 0.1 <= timeout <= 30
        ):
            raise ValueError("Provider timeout must be 0.1-30 seconds")
        if not isinstance(retries, int) or isinstance(retries, bool) or not 0 <= retries <= 3:
            raise ValueError("Provider retries must be 0-3")
        if (
            not isinstance(max_response_bytes, int)
            or isinstance(max_response_bytes, bool)
            or not 1 <= max_response_bytes <= _MAX_RESPONSE
        ):
            raise ValueError("Response limit must be 1-1048576 bytes")
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.retries = retries
        self.max_response_bytes = max_response_bytes

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: object = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> ProviderResponse:
        method = method.upper() if isinstance(method, str) else ""
        if method not in {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError("Unsupported HTTP method")
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            raise ValueError("Path must be relative to the trusted provider origin")
        parsed = urllib.parse.urlsplit(path)
        if (
            parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or any(segment in {".", ".."} for segment in parsed.path.split("/"))
        ):
            raise ValueError("Path cannot escape the configured HTTPS origin")
        if payload is not None and method in _SAFE_METHODS:
            raise ValueError("Safe HTTP methods cannot carry JSON request bodies")
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str) or not _KEY.fullmatch(idempotency_key)
        ):
            raise ValueError("Invalid provider idempotency key")
        if headers is not None and not isinstance(headers, dict):
            raise ValueError("Headers must be a trusted string mapping")
        provided = dict(headers or {})
        for key, value in provided.items():
            if (
                not isinstance(key, str)
                or not isinstance(value, str)
                or any(c in key + value for c in "\r\n")
                or key.lower() in {"host", "content-length", "connection", "transfer-encoding"}
            ):
                raise ValueError("Invalid HTTP header")
        body = None
        if payload is not None:
            try:
                body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise ValueError("JSON request payload is invalid") from exc
            if len(body) > _MAX_REQUEST:
                raise ValueError("Request body exceeds 64 KiB")
            provided["Content-Type"] = "application/json"
        if idempotency_key is not None:
            provided["Idempotency-Key"] = idempotency_key
        provided["Accept"] = "application/json"
        retry_allowed = method in _SAFE_METHODS or idempotency_key is not None
        attempts = self.retries + 1 if retry_allowed else 1
        url = self.base_url + path
        for attempt in range(attempts):
            request = urllib.request.Request(url, data=body, headers=provided, method=method)
            try:
                with _open(request, self.timeout) as response:
                    content = response.read(self.max_response_bytes + 1)
                    status = response.status
            except urllib.error.HTTPError as exc:
                status = exc.code
                content = exc.read(self.max_response_bytes + 1)
            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                http.client.HTTPException,
            ) as exc:
                if attempt + 1 < attempts:
                    time.sleep(min(0.25 * 2**attempt, 1.0))
                    continue
                raise ProviderTransportError("Provider request failed") from exc
            if len(content) > self.max_response_bytes:
                raise ProviderTransportError("Provider response exceeds allowed size")
            if status in _RETRYABLE and attempt + 1 < attempts:
                time.sleep(min(0.25 * 2**attempt, 1.0))
                continue
            return ProviderResponse(status=status, body=content)
        raise ProviderTransportError("Provider retries exhausted")
