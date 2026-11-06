from django.contrib import admin

from common.admin import ReadOnlyModelAdmin

from .models import PayrollLine, PayrollRun

# Payroll is created, approved and paid through payroll services (ADR 005).
# The admin is for inspection only.


class PayrollLineInline(admin.TabularInline):
    model = PayrollLine
    extra = 0
    can_delete = False
    fields = (
        "session",
        "hours_paid",
        "hourly_rate_applied",
        "gross_pay",
        "adjustment_amount",
        "final_amount",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(PayrollRun)
class PayrollRunAdmin(ReadOnlyModelAdmin):
    list_display = ("period_start", "period_end", "status", "created_by", "approved_by", "paid_at")
    list_filter = ("status",)
    inlines = (PayrollLineInline,)


@admin.register(PayrollLine)
class PayrollLineAdmin(ReadOnlyModelAdmin):
    list_display = ("payroll_run", "session", "hours_paid", "hourly_rate_applied", "final_amount")
