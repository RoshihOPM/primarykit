from rest_framework.permissions import BasePermission


class IsActiveSuperuser(BasePermission):
    message = "This action is restricted to active superusers."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_superuser)
