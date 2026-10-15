from django.contrib import admin

from .models import StoredFile


@admin.register(StoredFile)
class StoredFileAdmin(admin.ModelAdmin):
    list_display = ("created_at", "owner", "original_name", "size", "content_type", "deleted_at")
    search_fields = ("id", "object_key", "original_name")
    readonly_fields = (
        "id", "owner", "object_key", "original_name", "size",
        "content_type", "sha256", "created_at", "deleted_at",
    )

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
