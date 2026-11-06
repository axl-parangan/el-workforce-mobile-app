from django.contrib import admin

from .models import Job, JobAssignment


class JobAssignmentInline(admin.TabularInline):
    model = JobAssignment
    extra = 0
    fields = ("employee", "status", "start_date", "end_date", "assigned_by", "assigned_at")
    readonly_fields = ("assigned_by", "assigned_at")
    autocomplete_fields = ("employee",)


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("job_number", "name", "lead_hand", "status", "start_date", "end_date")
    list_filter = ("status",)
    search_fields = ("job_number", "name", "address")
    autocomplete_fields = ("lead_hand",)
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")
    inlines = (JobAssignmentInline,)
    fieldsets = (
        (None, {"fields": ("job_number", "name", "status", "lead_hand", "address")}),
        ("Schedule", {"fields": ("start_date", "end_date")}),
        (
            "Geofence (optional)",
            {"fields": ("latitude", "longitude", "geofence_radius_meters")},
        ),
        ("Audit", {"fields": ("created_by", "updated_by", "created_at", "updated_at")}),
    )

    def save_model(self, request, obj, form, change) -> None:
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change) -> None:
        for assignment in formset.save(commit=False):
            if assignment.assigned_by_id is None:
                assignment.assigned_by = request.user
            assignment.save()
        for deleted in formset.deleted_objects:
            deleted.delete()
        formset.save_m2m()


@admin.register(JobAssignment)
class JobAssignmentAdmin(admin.ModelAdmin):
    list_display = ("employee", "job", "status", "start_date", "end_date", "assigned_at")
    list_filter = ("status",)
    search_fields = ("employee__name", "job__job_number", "job__name")
    autocomplete_fields = ("employee", "job")
    readonly_fields = ("assigned_by", "assigned_at", "updated_at")

    def save_model(self, request, obj, form, change) -> None:
        if not change:
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)
