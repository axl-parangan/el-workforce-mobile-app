"""Assign employees to jobs and manage the assignment lifecycle.

Lifecycle (approved 2026-11-10):
- active  -> ended      (``end_assignment``): normal finish, keeps all history.
- active  -> cancelled  (``cancel_assignment``): assigned in error; only when
                         the assignment has no work sessions (Q7).
- Ended or cancelled assignments are never reactivated or deleted; assigning
  the employee again creates a new row (the database allows one *active*
  assignment per employee and job).
- Planned, active and on-hold jobs accept assignments (Q8). Completing or
  cancelling a job does not end its assignments.
- Ending or cancelling the designated LeadHand's assignment clears the job's
  LeadHand designation (Q4).
- An assignment can end while the employee is clocked in; they can still clock
  out of that session (Q5).
- Moving between jobs (clocking out of one, into another) never touches
  assignments.

Only users with ``assignments.manage`` (Managers, Admins) may change assignments.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status

from apps.accounts.authorization import Capability, has_capability
from apps.accounts.models import User
from apps.jobs.models import AssignmentStatus, Job, JobAssignment, JobStatus
from apps.workforce.models import Employee
from common.exceptions import ApplicationError
from common.timezones import work_date_for

ASSIGNABLE_JOB_STATUSES = frozenset({JobStatus.PLANNED, JobStatus.ACTIVE, JobStatus.ON_HOLD})


class AssignmentPermissionError(ApplicationError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "assignment_forbidden"


class AssignmentConflictError(ApplicationError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "assignment_conflict"


class AssignmentValidationError(ApplicationError):
    default_code = "validation_error"


@dataclass(frozen=True)
class AssignmentOutcome:
    employee: Employee
    assigned: bool
    code: str
    message: str
    assignment: JobAssignment | None


def require_assignable_job(job: Job) -> None:
    if job.status not in ASSIGNABLE_JOB_STATUSES:
        raise AssignmentConflictError(
            f"Job {job.job_number} is {job.get_status_display().lower()} and does not accept "
            "new assignments.",
            code="job_not_assignable",
        )


def ensure_active_assignment(*, job: Job, employee: Employee, actor: User) -> JobAssignment:
    """Return the employee's active assignment on the job, creating it if missing."""
    existing = JobAssignment.objects.filter(
        employee=employee, job=job, status=AssignmentStatus.ACTIVE
    ).first()
    if existing is not None:
        return existing
    return JobAssignment.objects.create(employee=employee, job=job, assigned_by=actor)


def _require_manage(actor: User) -> None:
    if not has_capability(actor, Capability.ASSIGNMENTS_MANAGE):
        raise AssignmentPermissionError("You are not allowed to manage assignments.")


def _check_dates(start_date: date | None, end_date: date | None) -> None:
    if start_date and end_date and end_date < start_date:
        raise AssignmentValidationError(
            "The end date cannot be before the start date.",
            details={"end_date": ["The end date cannot be before the start date."]},
        )


# --- Assign ---------------------------------------------------------------------------


def assign_employees(
    *,
    actor: User,
    job: Job,
    employees: list[Employee],
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[AssignmentOutcome]:
    """Assign several employees at once; each gets an individual outcome (Q10)."""
    _require_manage(actor)
    _check_dates(start_date, end_date)

    outcomes: list[AssignmentOutcome] = []
    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job.pk)
        require_assignable_job(job)
        for employee in employees:
            outcomes.append(
                _assign_one(actor=actor, job=job, employee=employee, start=start_date, end=end_date)
            )
    return outcomes


def _assign_one(*, actor, job, employee, start, end) -> AssignmentOutcome:
    if not employee.is_active:
        return AssignmentOutcome(
            employee, False, "employee_inactive", "The employee is inactive.", None
        )
    existing = JobAssignment.objects.filter(
        employee=employee, job=job, status=AssignmentStatus.ACTIVE
    ).first()
    if existing is not None:
        return AssignmentOutcome(
            employee,
            False,
            "already_assigned",
            f"Already actively assigned to job {job.job_number}.",
            existing,
        )
    try:
        with transaction.atomic():
            assignment = JobAssignment.objects.create(
                employee=employee, job=job, assigned_by=actor, start_date=start, end_date=end
            )
    except IntegrityError:
        # A concurrent request assigned the same employee first.
        existing = JobAssignment.objects.filter(
            employee=employee, job=job, status=AssignmentStatus.ACTIVE
        ).first()
        return AssignmentOutcome(
            employee,
            False,
            "already_assigned",
            f"Already actively assigned to job {job.job_number}.",
            existing,
        )
    return AssignmentOutcome(
        employee, True, "assigned", f"Assigned to job {job.job_number}.", assignment
    )


# --- Change dates ----------------------------------------------------------------------

_UNSET = object()


def update_assignment_dates(
    *, actor: User, assignment: JobAssignment, start_date=_UNSET, end_date=_UNSET
) -> JobAssignment:
    """Change the date window of an active assignment. Employee and job never change."""
    _require_manage(actor)
    with transaction.atomic():
        assignment = _locked_active(assignment)
        if start_date is not _UNSET:
            assignment.start_date = start_date
        if end_date is not _UNSET:
            assignment.end_date = end_date
        _check_dates(assignment.start_date, assignment.end_date)
        assignment.save(update_fields=["start_date", "end_date", "updated_at"])
    return assignment


# --- End and cancel ---------------------------------------------------------------------


def end_assignment(
    *, actor: User, assignment: JobAssignment, end_date: date | None = None
) -> JobAssignment:
    """Finish an active assignment on ``end_date`` (default: today, company timezone).

    The end date cannot be in the future: schedule a future end by editing the
    active assignment's ``end_date`` instead.
    """
    _require_manage(actor)
    today = work_date_for(timezone.now())
    end_date = end_date or today
    if end_date > today:
        raise AssignmentValidationError(
            "An assignment cannot be ended in the future. Set its end date instead.",
            code="end_date_in_future",
            details={"end_date": ["Must not be in the future."]},
        )
    with transaction.atomic():
        assignment = _locked_active(assignment)
        _check_dates(assignment.start_date, end_date)
        assignment.status = AssignmentStatus.ENDED
        assignment.end_date = end_date
        assignment.save(update_fields=["status", "end_date", "updated_at"])
        _clear_designation_if_lead(assignment, actor)
    return assignment


def cancel_assignment(*, actor: User, assignment: JobAssignment) -> JobAssignment:
    """Cancel an assignment made in error. Not allowed once attendance exists (Q7)."""
    _require_manage(actor)
    with transaction.atomic():
        assignment = _locked_active(assignment)
        if assignment.work_sessions.exists():
            raise AssignmentConflictError(
                "This assignment has attendance records. End it instead of cancelling it.",
                code="assignment_has_sessions",
            )
        assignment.status = AssignmentStatus.CANCELLED
        assignment.save(update_fields=["status", "updated_at"])
        _clear_designation_if_lead(assignment, actor)
    return assignment


def _locked_active(assignment: JobAssignment) -> JobAssignment:
    assignment = (
        JobAssignment.objects.select_for_update(of=("self",))
        .select_related("job", "employee")
        .get(pk=assignment.pk)
    )
    if assignment.status != AssignmentStatus.ACTIVE:
        raise AssignmentConflictError(
            f"This assignment is {assignment.get_status_display().lower()}.",
            code="assignment_not_active",
        )
    return assignment


def _clear_designation_if_lead(assignment: JobAssignment, actor: User) -> None:
    job = Job.objects.select_for_update().get(pk=assignment.job_id)
    if job.lead_hand_id == assignment.employee_id:
        job.lead_hand = None
        job.updated_by = actor
        job.save(update_fields=["lead_hand", "updated_by", "updated_at"])
