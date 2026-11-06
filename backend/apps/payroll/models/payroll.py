from django.conf import settings
from django.db import models
from django.db.models import F, Q


class PayrollRunStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    APPROVED = "approved", "Approved"
    PAID = "paid", "Paid"
    CANCELLED = "cancelled", "Cancelled"


class PayrollRun(models.Model):
    """Payroll for one period. Approved runs are never recalculated in place (ADR 005)."""

    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(
        max_length=16, choices=PayrollRunStatus.choices, default=PayrollRunStatus.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payroll_runs_created"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payroll_runs_approved",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-period_start",)
        constraints = [
            models.CheckConstraint(
                condition=Q(period_end__gte=F("period_start")),
                name="payroll_run_period_ordered",
            ),
            models.CheckConstraint(
                condition=Q(approved_by__isnull=True, approved_at__isnull=True)
                | Q(approved_by__isnull=False, approved_at__isnull=False),
                name="payroll_run_approver_and_time_together",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=(PayrollRunStatus.APPROVED, PayrollRunStatus.PAID))
                | Q(approved_at__isnull=False),
                name="payroll_run_approved_status_requires_approval",
            ),
            models.CheckConstraint(
                condition=Q(paid_at__isnull=True) | Q(approved_at__isnull=False),
                name="payroll_run_paid_requires_approval",
            ),
        ]

    def __str__(self) -> str:
        return f"Payroll {self.period_start} to {self.period_end} ({self.get_status_display()})"


class PayrollLine(models.Model):
    """Pay for one work session. Snapshots the hours and rate used (ADR 005).

    gross_pay = round_money(hours_paid x hourly_rate_applied);
    final_amount = gross_pay + adjustment_amount (enforced by the database).
    """

    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="lines")
    # A session is paid at most once.
    session = models.OneToOneField(
        "timekeeping.WorkSession", on_delete=models.PROTECT, related_name="payroll_line"
    )
    hours_paid = models.DecimalField(max_digits=9, decimal_places=4)
    hourly_rate_applied = models.DecimalField(max_digits=10, decimal_places=4)
    gross_pay = models.DecimalField(max_digits=12, decimal_places=2)
    adjustment_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    final_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(hours_paid__gte=0), name="payroll_line_hours_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(hourly_rate_applied__gte=0), name="payroll_line_rate_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(final_amount=F("gross_pay") + F("adjustment_amount")),
                name="payroll_line_final_is_gross_plus_adjustment",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.session}: {self.final_amount}"
