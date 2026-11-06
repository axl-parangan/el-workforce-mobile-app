from django.contrib import admin
from django.http import HttpRequest

from .models import CompanySettings


@admin.register(CompanySettings)
class CompanySettingsAdmin(admin.ModelAdmin):
    fields = ("workers_can_create_notes", "updated_at", "updated_by")
    readonly_fields = ("updated_at", "updated_by")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return not CompanySettings.objects.exists()

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def save_model(self, request, obj, form, change) -> None:
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
