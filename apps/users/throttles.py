from rest_framework.throttling import ScopedRateThrottle


class AccountRateThrottle(ScopedRateThrottle):
    """Basic DRF throttling; require a shared cache and edge protection in production."""
