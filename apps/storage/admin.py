from django.contrib import admin

from apps.organizations.models import Membership

from .models import StoredFile


@admin.register(StoredFile)
class StoredFileAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "organization", "owner", "original_name", "size", "content_type", "deleted_at"
    )
    search_fields = ("id", "object_key", "original_name")
    readonly_fields = (
        "id",
        "organization",
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
        return super().get_queryset(request).filter(
            organization__is_active=True,
            organization__memberships__user=request.user,
            organization__memberships__is_active=True,
            organization__memberships__role__in=(Membership.Role.OWNER, Membership.Role.ADMIN),
        )

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
