"""Role-based model permission and owner scoping primitives for feature APIs."""

from rest_framework.permissions import BasePermission


class HasRequiredPermissions(BasePermission):
    """Permission codes must be declared for each view/method; fail closed."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        permissions = getattr(view, "required_permissions", None)
        if not isinstance(permissions, dict):
            return False
        codes = permissions.get(request.method)
        if not codes or not isinstance(codes, (tuple, list, set)):
            return False
        return user.has_perms(codes)


class OwnerScopedQuerysetMixin:
    """Scope list/detail queries to owner unless explicit per-method global permission.

    Subclasses must declare owner_lookup and global_scope_permissions. Never use this
    to justify assigning client-controlled owner fields on create.
    """

    owner_lookup = None
    global_scope_permissions = None

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user or not user.is_authenticated or not user.is_active:
            return qs.none()
        if user.is_superuser:
            return qs
        if not self.owner_lookup:
            raise AssertionError("OwnerScopedQuerysetMixin requires owner_lookup")
        global_perm = (self.global_scope_permissions or {}).get(self.request.method)
        if global_perm and user.has_perm(global_perm):
            return qs
        return qs.filter(**{self.owner_lookup: user.pk})


class IsOwnerOrGlobalPermission(BasePermission):
    """Object-level check as defense in depth; lists require OwnerScopedQuerysetMixin."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user.is_active:
            return False
        if user.is_superuser:
            return True
        global_perm = (getattr(view, "global_scope_permissions", None) or {}).get(request.method)
        if global_perm and user.has_perm(global_perm):
            return True
        owner_attribute = getattr(view, "owner_attribute", None)
        if not owner_attribute:
            return False
        return getattr(obj, owner_attribute, None) == user.pk
