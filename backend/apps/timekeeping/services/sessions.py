"""Per-employee attendance rules: open and close work sessions.

Called by services.attendance for each AttendanceBatchItem, inside the
batch's transaction and while holding a row lock on the employee, so all
attendance writes for one employee are serialised.

Every outcome is written to the item (status, code, message) so that a retry
of the same event returns exactly the same result.

Time is always the batch's ``captured_at`` (device time), never the server's
receipt time, so offline events reconstruct the real work period.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from django.db.models import Q
from django.utils import timezone

from apps.jobs.models import AssignmentStatus, JobAssignment, JobStatus
from apps.timekeeping.models import (
    AttendanceBatchItem,
    BatchItemResult,
    ItemResultCode,
    PunchType,
    ReviewStatus,
    SessionExceptionFlag,
    SessionStatus,
    TimePunch,
    WorkSession,
)
from apps.timekeeping.selectors.attendance import with_punch_times
from common.timezones import to_company_time, work_date_for


def process_item(item: AttendanceBatchItem, *, exception_flags: Iterable[str] = ()) -> None:
    """Apply the batch's action to the item's employee and record the outcome on the item.

    ``exception_flags`` are batch-level review reasons (location, device time)
    added to whichever session the punch lands in.
    """
    if item.batch.action_type == PunchType.CLOCK_IN:
        _clock_in(item, exception_flags=tuple(exception_flags))
    else:
        _clock_out(item, exception_flags=tuple(exception_flags))


def add_exception_flags(session: WorkSession, flags: Iterable[str]) -> None:
    """Merge flags into the session (sorted, no duplicates) and queue it for review."""
    merged = sorted(set(session.exception_flags) | set(flags))
    if merged == sorted(session.exception_flags):
        return
    session.exception_flags = merged
    session.review_status = ReviewStatus.PENDING
    session.save(update_fields=["exception_flags", "review_status", "updated_at"])


# --- Clock-in ----------------------------------------------------------------------


def _clock_in(item: AttendanceBatchItem, *, exception_flags: tuple[str, ...]) -> None:
    batch, employee = item.batch, item.employee
    at = batch.captured_at

    if not employee.is_active:
        return _reject(item, ItemResultCode.EMPLOYEE_INACTIVE, "The employee is inactive.")
    if batch.job.status != JobStatus.ACTIVE:
        return _reject(
            item,
            ItemResultCode.JOB_NOT_ACTIVE,
            f"Job {batch.job.job_number} is {batch.job.get_status_display().lower()}.",
        )

    assignment = (
        JobAssignment.objects.filter(
            employee=employee, job=batch.job, status=AssignmentStatus.ACTIVE
        )
        .order_by("-assigned_at")
        .first()
    )
    if assignment is None:
        return _reject(
            item,
            ItemResultCode.NO_ACTIVE_ASSIGNMENT,
            f"The employee has no active assignment to job {batch.job.job_number}.",
        )
    item.assignment = assignment

    work_date = work_date_for(at)
    if (assignment.start_date and work_date < assignment.start_date) or (
        assignment.end_date and work_date > assignment.end_date
    ):
        return _reject(
            item,
            ItemResultCode.ASSIGNMENT_NOT_IN_EFFECT,
            f"The assignment to job {batch.job.job_number} is not in effect on {work_date}.",
        )

    open_session = _open_session(employee)
    if open_session is not None:
        return _reject(
            item,
            ItemResultCode.ALREADY_CLOCKED_IN,
            f"Already clocked in to job {open_session.assignment.job.job_number} "
            f"since {_fmt(open_session.clock_in_at)}.",
        )

    overlapping = _sessions_overlapping(employee, start=at, end=at).first()
    if overlapping is not None:
        return _reject(
            item,
            ItemResultCode.OVERLAPS_EXISTING_SESSION,
            f"{_fmt(at)} falls inside an existing session "
            f"({_fmt(overlapping.clock_in_at)} to {_fmt(overlapping.clock_out_at)}).",
        )

    session = WorkSession.objects.create(
        assignment=assignment, work_date=work_date, session_status=SessionStatus.OPEN
    )
    _accept(item, session, ItemResultCode.CLOCKED_IN, f"Clocked in at {_fmt(at)}.")
    add_exception_flags(session, exception_flags)


# --- Clock-out ---------------------------------------------------------------------


def _clock_out(item: AttendanceBatchItem, *, exception_flags: tuple[str, ...]) -> None:
    batch, employee = item.batch, item.employee
    at = batch.captured_at

    session = _open_session(employee, lock=True)
    if session is None:
        return _reject(
            item, ItemResultCode.NO_OPEN_SESSION, "There is no open session to clock out of."
        )
    if session.assignment.job_id != batch.job_id:
        return _reject(
            item,
            ItemResultCode.OPEN_SESSION_ON_OTHER_JOB,
            f"The open session is on job {session.assignment.job.job_number}, "
            f"not {batch.job.job_number}.",
        )
    item.assignment = session.assignment

    # Irreconcilable clock-outs are rejected (never producing a wrong session)
    # and the open session is flagged so a reviewer can see it.
    if at < session.clock_in_at:
        _reject(
            item,
            ItemResultCode.CLOCK_OUT_BEFORE_CLOCK_IN,
            f"Clock-out at {_fmt(at)} is before the clock-in at {_fmt(session.clock_in_at)}.",
        )
        return add_exception_flags(session, [SessionExceptionFlag.CLOCK_OUT_REJECTED])

    overlapping = (
        _sessions_overlapping(employee, start=session.clock_in_at, end=at)
        .exclude(pk=session.pk)
        .first()
    )
    if overlapping is not None:
        _reject(
            item,
            ItemResultCode.OVERLAPS_EXISTING_SESSION,
            f"Closing the session at {_fmt(at)} would overlap another session "
            f"({_fmt(overlapping.clock_in_at)} to {_fmt(overlapping.clock_out_at)}).",
        )
        return add_exception_flags(session, [SessionExceptionFlag.CLOCK_OUT_REJECTED])

    session.session_status = SessionStatus.CLOSED
    session.save(update_fields=["session_status", "updated_at"])
    _accept(item, session, ItemResultCode.CLOCKED_OUT, f"Clocked out at {_fmt(at)}.")
    add_exception_flags(session, exception_flags)


# --- Helpers ------------------------------------------------------------------------


def _open_session(employee, *, lock: bool = False) -> WorkSession | None:
    queryset = WorkSession.objects.filter(
        assignment__employee=employee, session_status=SessionStatus.OPEN
    ).select_related("assignment__job")
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    return with_punch_times(queryset).order_by("-created_at").first()


def _sessions_overlapping(employee, *, start: datetime, end: datetime):
    """Closed sessions of the employee that intersect [start, end].

    Touching boundaries (one session ending exactly when the next begins) do
    not count as overlap.
    """
    return (
        with_punch_times(
            WorkSession.objects.filter(
                assignment__employee=employee, session_status=SessionStatus.CLOSED
            )
        )
        .filter(Q(clock_in_at__lt=end) | Q(clock_in_at=start))
        .filter(clock_out_at__gt=start)
        .order_by("clock_in_at")
    )


def _accept(item: AttendanceBatchItem, session: WorkSession, code: str, message: str) -> None:
    TimePunch.objects.create(session=session, batch_item=item, punch_type=item.batch.action_type)
    item.result_status = BatchItemResult.ACCEPTED
    item.result_code = code
    item.result_message = message
    item.processed_at = timezone.now()
    item.save()


def _reject(item: AttendanceBatchItem, code: str, message: str) -> None:
    item.result_status = BatchItemResult.REJECTED
    item.result_code = code
    item.result_message = message
    item.processed_at = timezone.now()
    item.save()


def _fmt(instant: datetime | None) -> str:
    """Human-readable time in the company timezone for result messages."""
    if instant is None:
        return "unknown time"
    return to_company_time(instant).strftime("%Y-%m-%d %H:%M %Z")
