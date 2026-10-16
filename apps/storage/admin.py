from django.apps import apps as django_apps
from django.contrib import admin
from django.db.models import Q

from .models import StoredFile


@admin.register(StoredFile)
class StoredFileAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "organization_id",
        "owner",
        "original_name",
        "size",
        "content_type",
        "deleted_at",
    )
    search_fields = ("id", "object_key", "original_name")
    readonly_fields = (
        "id",
        "organization_id",
        "owner",
        "object_key",
        "original_name",
        "size",
        "content_type",
        "sha256",
        "created_at",
        "deleted_at",
    )

    def get_queryset(self, request):
        # Django admin is never a backdoor across personal or tenant boundaries.
        allowed = Q(organization_id__isnull=True, owner=request.user)
        if django_apps.is_installed("apps.organizations"):
            from apps.organizations.models import Membership

            org_ids = Membership.objects.filter(
                user=request.user,
                is_active=True,
                organization__is_active=True,
                role__in=(Membership.Role.OWNER, Membership.Role.ADMIN),
            ).values_list("organization_id", flat=True)
            allowed |= Q(organization_id__in=org_ids)
        return super().get_queryset(request).filter(allowed)

    def has_view_permission(self, request, obj=None):
        if not (request.user.is_active and request.user.is_superuser):
            return False
        return obj is None or self.get_queryset(request).filter(pk=obj.pk).exists()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
