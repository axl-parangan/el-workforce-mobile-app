from django.contrib import admin

from .models import Employee


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("name", "employee_number", "user", "hourly_rate", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "employee_number", "user__email")
    autocomplete_fields = ("user",)
