"""Account throttling can switch to atomic Redis across API worker processes."""

from django.conf import settings
from rest_framework.throttling import ScopedRateThrottle


class AccountRateThrottle(ScopedRateThrottle):
    """DRF local-cache fallback is for development, not shared production enforcement."""

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
            # Never trust a client-controlled X-Forwarded-For; reverse proxies
            # should set REMOTE_ADDR to the verified client IP.
            identity = f"ip:{request.META.get('REMOTE_ADDR', 'unknown')}"
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
