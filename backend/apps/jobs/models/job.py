from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.accounts.authorization import Capability, has_capability
from apps.jobs.constants import DEFAULT_GEOFENCE_RADIUS_METERS


class JobStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    ACTIVE = "active", "Active"
    ON_HOLD = "on_hold", "On hold"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class Job(models.Model):
    """A construction job.

    - One optional LeadHand per job (an employee whose user may lead jobs). They
      manage the job only while they also hold an active assignment on it
      (apps/jobs/selectors/scope.py).
    - The geofence is optional (ADR 004): latitude/longitude are both set or
      both empty; the radius defaults to 100 m and is customisable per job.
    - Jobs are not linked to clients (ADR 010).
    """

    job_number = models.CharField(max_length=50, unique=True)
    lead_hand = models.ForeignKey(
        "workforce.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="led_jobs",
    )
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geofence_radius_meters = models.PositiveIntegerField(
        null=True, blank=True, default=DEFAULT_GEOFENCE_RADIUS_METERS
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=JobStatus.choices, default=JobStatus.ACTIVE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="jobs_created"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="jobs_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("job_number",)
        constraints = [
            models.CheckConstraint(
                condition=Q(latitude__isnull=True, longitude__isnull=True)
                | Q(latitude__isnull=False, longitude__isnull=False),
                name="jobs_job_coordinates_both_or_neither",
            ),
            models.CheckConstraint(
                condition=Q(latitude__isnull=True) | Q(latitude__gte=-90, latitude__lte=90),
                name="jobs_job_latitude_range",
            ),
            models.CheckConstraint(
                condition=Q(longitude__isnull=True) | Q(longitude__gte=-180, longitude__lte=180),
                name="jobs_job_longitude_range",
            ),
            models.CheckConstraint(
                condition=Q(geofence_radius_meters__isnull=True) | Q(geofence_radius_meters__gt=0),
                name="jobs_job_radius_positive",
            ),
            models.CheckConstraint(
                condition=Q(start_date__isnull=True)
                | Q(end_date__isnull=True)
                | Q(end_date__gte=F("start_date")),
                name="jobs_job_dates_ordered",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.job_number} - {self.name}"

    def clean(self) -> None:
        super().clean()
        if self.lead_hand_id is not None:
            user = self.lead_hand.user
            if not has_capability(user, Capability.JOBS_LEAD):
                raise ValidationError(
                    {"lead_hand": "The LeadHand must be an employee with a LeadHand user account."}
                )
