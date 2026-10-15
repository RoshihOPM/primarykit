from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "action", "actor", "target_type", "target_id")
    list_filter = ("action", "target_type", "occurred_at")
    search_fields = ("target_id", "action")
    readonly_fields = (
        "id",
        "occurred_at",
        "actor",
        "action",
        "target_type",
        "target_id",
        "changes",
    )

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
