from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class AssignmentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ENDED = "ended", "Ended"
    CANCELLED = "cancelled", "Cancelled"


class JobAssignment(models.Model):
    """Assigns an employee to a job. Work sessions are authorised by an assignment."""

    employee = models.ForeignKey(
        "workforce.Employee", on_delete=models.PROTECT, related_name="job_assignments"
    )
    job = models.ForeignKey("jobs.Job", on_delete=models.PROTECT, related_name="assignments")
    assigned_at = models.DateTimeField(default=timezone.now)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=AssignmentStatus.choices, default=AssignmentStatus.ACTIVE
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assignments_made"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-assigned_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("employee", "job"),
                condition=Q(status=AssignmentStatus.ACTIVE),
                name="jobs_assignment_one_active_per_employee_job",
            ),
            models.CheckConstraint(
                condition=Q(start_date__isnull=True)
                | Q(end_date__isnull=True)
                | Q(end_date__gte=F("start_date")),
                name="jobs_assignment_dates_ordered",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee} → {self.job}"
