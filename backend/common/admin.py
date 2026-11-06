from django.contrib import admin
from django.http import HttpRequest


class ReadOnlyModelAdmin(admin.ModelAdmin):
    """For records that must only change through services (immutable or calculated data)."""

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False
