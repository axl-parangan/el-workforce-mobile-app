"""Create and edit jobs, and designate their LeadHand.

Rules (approved 2026-11-10):
- Q1  A LeadHand who creates a job becomes its designated LeadHand and gets an
      active assignment to it, so they manage the job from the start.
- Q2  Job numbers are entered by hand (generation is deferred).
- Q3  LeadHands may set/edit only name, address, start and end dates (plus the
      job number when creating). Managers and Admins may set every field.
- Q4  Designating a LeadHand creates their assignment if needed; replacing a
      LeadHand leaves the previous one's assignment untouched.

Who may act at all is a capability; which jobs is decided by scope selectors.
"""

from __future__ import annotations

from django.db import transaction
from rest_framework import status

from apps.accounts.authorization import Capability, has_capability
from apps.accounts.models import User
from apps.jobs.models import Job
from apps.jobs.selectors.scope import jobs_editable_by
from apps.workforce.models import Employee
from common.exceptions import ApplicationError

from .assignments import ensure_active_assignment, require_assignable_job

# Fields a LeadHand may edit on jobs they manage (Q3).
MANAGED_EDIT_FIELDS = frozenset({"name", "address", "start_date", "end_date"})
# Fields Managers and Admins may edit.
ALL_EDIT_FIELDS = MANAGED_EDIT_FIELDS | {
    "job_number",
    "status",
    "latitude",
    "longitude",
    "geofence_radius_meters",
}


class JobPermissionError(ApplicationError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "job_forbidden"


class LeadHandNotEligibleError(ApplicationError):
    default_code = "not_eligible_lead_hand"


def editable_fields(user: User) -> frozenset[str]:
    if has_capability(user, Capability.JOBS_EDIT_ANY):
        return ALL_EDIT_FIELDS
    if has_capability(user, Capability.JOBS_EDIT_MANAGED):
        return MANAGED_EDIT_FIELDS
    return frozenset()


def _require_fields_allowed(user: User, fields: set[str], *, creating: bool) -> None:
    allowed = editable_fields(user)
    if creating:
        allowed = allowed | {"job_number"}
    forbidden = sorted(fields - allowed)
    if forbidden:
        raise JobPermissionError(
            "You are not allowed to set some of these fields.",
            code="field_not_editable",
            details={"fields": forbidden},
        )


def create_job(*, actor: User, data: dict, lead_hand: Employee | None = None) -> Job:
    """Create a job. ``data`` holds model field values validated by the API layer."""
    if not has_capability(actor, Capability.JOBS_CREATE):
        raise JobPermissionError("You are not allowed to create jobs.")
    _require_fields_allowed(actor, set(data), creating=True)
    if lead_hand is not None and not has_capability(actor, Capability.ASSIGNMENTS_MANAGE):
        raise JobPermissionError(
            "You are not allowed to designate a LeadHand.", code="field_not_editable"
        )

    # Q1: a LeadHand creator leads (and is assigned to) the job they create.
    creator_leads = has_capability(actor, Capability.JOBS_LEAD)
    creator_employee = None
    if creator_leads:
        creator_employee = Employee.objects.filter(user=actor).first()
        if creator_employee is None:
            raise JobPermissionError(
                "Your account is not linked to an employee record.", code="no_employee_profile"
            )

    with transaction.atomic():
        job = Job(**data, created_by=actor, updated_by=actor)
        job.full_clean()
        job.save()
        if creator_employee is not None:
            _designate(job=job, employee=creator_employee, actor=actor)
        elif lead_hand is not None:
            _designate(job=job, employee=lead_hand, actor=actor)
    return job


def update_job(*, actor: User, job: Job, data: dict) -> Job:
    """Edit a job's fields. LeadHands only on jobs they manage, and only Q3 fields."""
    if not jobs_editable_by(actor).filter(pk=job.pk).exists():
        raise JobPermissionError("You are not allowed to edit this job.", code="job_not_editable")
    _require_fields_allowed(actor, set(data), creating=False)

    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job.pk)
        for field, value in data.items():
            setattr(job, field, value)
        job.updated_by = actor
        job.full_clean()
        job.save()
    return job


def designate_lead_hand(*, actor: User, job: Job, employee: Employee | None) -> Job:
    """Set, replace or clear (``employee=None``) a job's LeadHand (Managers and Admins)."""
    if not has_capability(actor, Capability.ASSIGNMENTS_MANAGE):
        raise JobPermissionError("You are not allowed to designate LeadHands.")
    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job.pk)
        if employee is None:
            job.lead_hand = None
            job.updated_by = actor
            job.save(update_fields=["lead_hand", "updated_by", "updated_at"])
        else:
            _designate(job=job, employee=employee, actor=actor)
    return job


def _designate(*, job: Job, employee: Employee, actor: User) -> None:
    """Make ``employee`` the job's LeadHand, assigning them first if needed (Q4).

    The previous LeadHand's assignment is left as it is: they stay on the crew.
    Caller holds the job row lock or has just created the job.
    """
    employee = Employee.objects.select_related("user").get(pk=employee.pk)
    if not employee.is_active or not has_capability(employee.user, Capability.JOBS_LEAD):
        raise LeadHandNotEligibleError(
            "Only an active employee with an active LeadHand account can lead a job.",
            details={"employee_id": [str(employee.pk)]},
        )
    require_assignable_job(job)
    ensure_active_assignment(job=job, employee=employee, actor=actor)
    job.lead_hand = employee
    job.updated_by = actor
    job.save(update_fields=["lead_hand", "updated_by", "updated_at"])
