from rest_framework.permissions import SAFE_METHODS, BasePermission


class CatalogAccess(BasePermission):
    """Read: verified authenticated users. Write: active superusers only."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        return request.method in SAFE_METHODS or user.is_superuser
