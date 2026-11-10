from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .choices import (
    ACCEPTED_RESULT_CODES,
    BatchItemResult,
    BatchSource,
    ItemResultCode,
    LocationStatus,
    PunchType,
)


class AttendanceBatch(models.Model):
    """One clock-in/clock-out action performed on a device (ADR 003, 006).

    An individual punch is a batch with one item; a LeadHand group punch is a
    batch with one item per selected employee. The location belongs to the
    performer's device. Batches are immutable once received.
    """

    # Client-generated; makes offline retries idempotent (ADR 002).
    idempotency_key = models.UUIDField(unique=True)
    job = models.ForeignKey("jobs.Job", on_delete=models.PROTECT, related_name="attendance_batches")
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_batches"
    )
    action_type = models.CharField(max_length=16, choices=PunchType.choices)
    source = models.CharField(max_length=24, choices=BatchSource.choices)
    # Device timestamp (audit; also the instant the work date is derived from).
    captured_at = models.DateTimeField()
    received_at = models.DateTimeField(default=timezone.now)
    # Optional explanation, mainly for administrative entries (source=admin_entry).
    entry_reason = models.TextField(blank=True, default="")

    # Sanitised by assess_punch_location: invalid values are stored as NULL.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    accuracy_meters = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    distance_meters = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    location_status = models.CharField(max_length=32, choices=LocationStatus.choices)
    # Every condition that applied; location_status is the primary one.
    location_flags = ArrayField(
        models.CharField(max_length=32, choices=LocationStatus.choices),
        default=list,
        blank=True,
    )

    class Meta:
        ordering = ("-captured_at",)
        verbose_name_plural = "attendance batches"
        constraints = [
            models.CheckConstraint(
                condition=Q(latitude__isnull=True, longitude__isnull=True)
                | Q(latitude__isnull=False, longitude__isnull=False),
                name="timekeeping_batch_coordinates_both_or_neither",
            ),
            models.CheckConstraint(
                condition=Q(accuracy_meters__isnull=True)
                | Q(latitude__isnull=False, accuracy_meters__gte=0),
                name="timekeeping_batch_accuracy_requires_coordinates",
            ),
            models.CheckConstraint(
                condition=Q(distance_meters__isnull=True)
                | Q(latitude__isnull=False, distance_meters__gte=0),
                name="timekeeping_batch_distance_requires_coordinates",
            ),
        ]
        indexes = [models.Index(fields=("job", "captured_at"))]

    def __str__(self) -> str:
        return f"{self.get_action_type_display()} on {self.job} by {self.performed_by}"


class AttendanceBatchItem(models.Model):
    """The outcome of a batch for one employee. Accepted items generate one TimePunch."""

    batch = models.ForeignKey(AttendanceBatch, on_delete=models.PROTECT, related_name="items")
    employee = models.ForeignKey(
        "workforce.Employee", on_delete=models.PROTECT, related_name="attendance_batch_items"
    )
    # The assignment the employee was validated against (null when none matched).
    assignment = models.ForeignKey(
        "jobs.JobAssignment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attendance_batch_items",
    )
    result_status = models.CharField(
        max_length=16, choices=BatchItemResult.choices, default=BatchItemResult.PENDING
    )
    # Stable code for clients (empty while pending). Never changed once processed.
    result_code = models.CharField(
        max_length=40, choices=ItemResultCode.choices, blank=True, default=""
    )
    result_message = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("batch", "employee"), name="timekeeping_item_one_per_employee_per_batch"
            ),
            models.CheckConstraint(
                condition=~Q(result_status=BatchItemResult.ACCEPTED)
                | Q(assignment__isnull=False, processed_at__isnull=False),
                name="timekeeping_item_accepted_requires_assignment",
            ),
            models.CheckConstraint(
                condition=~Q(result_status=BatchItemResult.ACCEPTED)
                | Q(result_code__in=ACCEPTED_RESULT_CODES),
                name="timekeeping_item_accepted_has_accepted_code",
            ),
            models.CheckConstraint(
                condition=~Q(result_status=BatchItemResult.REJECTED)
                | (~Q(result_code="") & ~Q(result_code__in=ACCEPTED_RESULT_CODES)),
                name="timekeeping_item_rejected_has_rejection_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee}: {self.get_result_status_display()}"
