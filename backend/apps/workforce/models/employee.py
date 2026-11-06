from django.conf import settings
from django.db import models


class Employee(models.Model):
    """A person employed by the company: workers and LeadHands (ADR 007).

    The user account is optional: employees without one have their attendance
    recorded by a LeadHand. LeadHands and self-clocking workers need one.

    Pay (ADR 005, MVP): a single current hourly rate, as in the ERD. Approved
    payroll is protected by the rate snapshot on PayrollLine. Compensation
    types and effective-dated rate history are deferred.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employee",
    )
    # Separate, non-secret identifier; never a login credential.
    employee_number = models.CharField(max_length=32, unique=True, null=True, blank=True)
    name = models.CharField(max_length=200)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=4)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(hourly_rate__gte=0), name="workforce_employee_rate_non_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.employee_number})" if self.employee_number else self.name

    def save(self, *args, **kwargs) -> None:
        # Blank form input must not collide on the unique constraint.
        if not self.employee_number:
            self.employee_number = None
        super().save(*args, **kwargs)
