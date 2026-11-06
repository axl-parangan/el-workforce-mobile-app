from django.contrib import admin

from common.admin import ReadOnlyModelAdmin

from .models import (
    AttendanceBatch,
    AttendanceBatchItem,
    TimePunch,
    WorkSession,
    WorkSessionReview,
)

# Attendance records are written only by timekeeping services. The admin is
# for inspection; reviews and corrections will get dedicated workflows.


class AttendanceBatchItemInline(admin.TabularInline):
    model = AttendanceBatchItem
    extra = 0
    can_delete = False
    fields = (
        "employee",
        "assignment",
        "result_status",
        "result_code",
        "result_message",
        "processed_at",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(AttendanceBatch)
class AttendanceBatchAdmin(ReadOnlyModelAdmin):
    list_display = (
        "captured_at",
        "action_type",
        "job",
        "performed_by",
        "source",
        "location_status",
    )
    list_filter = ("action_type", "source", "location_status")
    search_fields = ("idempotency_key", "job__job_number", "performed_by__email")
    date_hierarchy = "captured_at"
    inlines = (AttendanceBatchItemInline,)


@admin.register(AttendanceBatchItem)
class AttendanceBatchItemAdmin(ReadOnlyModelAdmin):
    list_display = ("batch", "employee", "result_status", "result_code", "processed_at")
    list_filter = ("result_status", "result_code")
    search_fields = ("employee__name", "batch__idempotency_key")


class WorkSessionReviewInline(admin.TabularInline):
    model = WorkSessionReview
    extra = 0
    can_delete = False
    fields = ("reviewed_at", "decision", "reason", "reviewed_by")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(WorkSession)
class WorkSessionAdmin(ReadOnlyModelAdmin):
    list_display = (
        "work_date",
        "assignment",
        "session_status",
        "review_status",
        "exception_flags",
        "reviewed_by",
    )
    inlines = (WorkSessionReviewInline,)
    list_filter = ("session_status", "review_status")
    search_fields = ("assignment__employee__name", "assignment__job__job_number")
    date_hierarchy = "work_date"


@admin.register(TimePunch)
class TimePunchAdmin(ReadOnlyModelAdmin):
    list_display = ("session", "punch_type", "batch_item")
    list_filter = ("punch_type",)


@admin.register(WorkSessionReview)
class WorkSessionReviewAdmin(ReadOnlyModelAdmin):
    """Append-only audit log; reviews are made through the staff review endpoint."""

    list_display = ("reviewed_at", "session", "decision", "reviewed_by")
    list_filter = ("decision",)
    search_fields = ("reason", "session__assignment__employee__name")
