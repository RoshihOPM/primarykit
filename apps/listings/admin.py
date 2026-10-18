from django.contrib import admin

from .models import Listing, ListingCategory


@admin.register(ListingCategory)
class ListingCategoryAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "active")
    search_fields = ("slug", "title")


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "category", "status", "price_minor", "currency")
    list_filter = ("status", "category")
    search_fields = ("title",)
    readonly_fields = ("status", "version", "published_at", "closed_at")

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
