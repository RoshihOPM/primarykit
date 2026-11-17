"""Account throttling can switch to atomic Redis across API worker processes."""

import ipaddress

from django.conf import settings
from rest_framework.settings import api_settings
from rest_framework.throttling import ScopedRateThrottle


def client_ident(request) -> str:
    """Return the anonymous throttle identity for both local and shared modes.

    ``REST_FRAMEWORK["NUM_PROXIES"]`` (env ``DJANGO_NUM_PROXIES``, default 0) is
    the number of trusted reverse-proxy hops that append to ``X-Forwarded-For``.
    With 0 the header is ignored. With N >= 1 only the N-th address from the
    right is used: everything further left is client-supplied. A header that is
    absent, shorter than N or not an IP address at that position means the
    request did not come through the declared chain, so the directly connected
    peer is used instead of a value the caller could pick.
    """
    remote = request.META.get("REMOTE_ADDR") or "unknown"
    hops = api_settings.NUM_PROXIES
    # DRF reads None as "trust the whole header"; here it means no trusted hop.
    if type(hops) is not int or hops < 1:
        return remote
    addresses = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")
    if len(addresses) < hops:
        return remote
    try:
        return str(ipaddress.ip_address(addresses[-hops].strip()))
    except ValueError:
        return remote


class AccountRateThrottle(ScopedRateThrottle):
    """DRF local-cache fallback is for development, not shared production enforcement."""

    def get_ident(self, request):
        return client_ident(request)

    def allow_request(self, request, view):
        if not getattr(settings, "SHARED_ACCOUNT_THROTTLE_ENABLED", False):
            return super().allow_request(request, view)
        from apps.rate_limit.services import check_limit

        self.scope = getattr(view, "throttle_scope", None)
        if self.scope is None:
            return True
        rate = self.get_rate()
        if rate is None:
            return True
        limit, duration = self.parse_rate(rate)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            identity = f"user:{user.pk}"
        else:
            identity = f"ip:{client_ident(request)}"
        accepted, self.retry_after = check_limit(
            scope=self.scope,
            identity=identity,
            max_requests=limit,
            window_seconds=duration,
        )
        return accepted

    def wait(self):
        if getattr(settings, "SHARED_ACCOUNT_THROTTLE_ENABLED", False):
            return getattr(self, "retry_after", None)
        return super().wait()
