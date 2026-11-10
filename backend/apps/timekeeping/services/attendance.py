"""Record an attendance event: the single entry point for every punch.

Online clock-in/out, LeadHand group clock-in/out and offline sync all call
``record_attendance``. One event becomes one AttendanceBatch with one item per
employee (ADR 003, 006).

Idempotency (ADR 002): the client-generated ``event_id`` is stored as
``AttendanceBatch.idempotency_key`` (unique). Re-sending an event returns the
stored batch and its items unchanged. A concurrent duplicate blocks on the
unique index until the first transaction commits, then replays its result.

Who may record what (ADR 011): everyone with an employee record records their
own attendance; LeadHands record for the crew of jobs they manage; Admins and
Managers record for anyone. A company-wide user's entry for someone else is an
administrative entry (``source = admin_entry``): its location is stored but
not used to flag sessions, and it must be current (no backdating).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status

from apps.accounts.authorization import Capability, has_any_capability, has_capability
from apps.accounts.models import User
from apps.jobs.models import Job
from apps.jobs.selectors.scope import can_record_attendance_for_others
from apps.timekeeping.models import (
    AttendanceBatch,
    AttendanceBatchItem,
    BatchSource,
    PunchType,
    SessionExceptionFlag,
)
from apps.timekeeping.selectors.attendance import batch_with_items, employee_for_user
from apps.timekeeping.services.location_validation import (
    LocationAssessment,
    assess_punch_location,
    build_job_geofence,
)
from apps.timekeeping.services.sessions import process_item
from apps.workforce.models import Employee
from common.exceptions import ApplicationError


class AttendanceForbiddenError(ApplicationError):
    """The actor may not record this event at all (nothing is stored)."""

    status_code = status.HTTP_403_FORBIDDEN
    default_code = "attendance_forbidden"


class AdminEntryNotCurrentError(ApplicationError):
    """An Admin/Manager entry for other employees is too old (backdating is not allowed)."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "admin_entry_not_current"


class IdempotencyConflictError(ApplicationError):
    """The event_id was already used for a different event or by a different user."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "idempotency_key_conflict"


@dataclass(frozen=True)
class AttendanceEvent:
    """A validated attendance event, before processing.

    ``employees`` is None for a self punch: the employee is always derived from
    the authenticated user, never taken from the client.
    """

    event_id: uuid.UUID
    action_type: str
    job: Job
    captured_at: datetime
    employees: tuple[Employee, ...] | None = None
    # Raw, unvalidated location values; see location_validation.
    latitude: object = None
    longitude: object = None
    accuracy_meters: object = None
    # Optional note, mainly for administrative entries.
    reason: str = ""

    @property
    def is_group(self) -> bool:
        return self.employees is not None


@dataclass(frozen=True)
class AttendanceResult:
    batch: AttendanceBatch
    replayed: bool


def record_attendance(
    *, actor: User, event: AttendanceEvent, source: str = BatchSource.MOBILE_ONLINE
) -> AttendanceResult:
    existing = AttendanceBatch.objects.filter(idempotency_key=event.event_id).first()
    if existing is not None:
        return _replay(existing, actor=actor, event=event)

    employees = _authorized_employees(actor, event)
    received_at = timezone.now()
    if _is_admin_entry(actor, employees):
        source = BatchSource.ADMIN_ENTRY
        _require_current_admin_entry(event, received_at)

    assessment = _location_assessment(event)
    try:
        with transaction.atomic():
            batch = _create_batch(
                actor=actor,
                event=event,
                source=source,
                assessment=assessment,
                received_at=received_at,
            )
            flags = _batch_exception_flags(batch, assessment)
            # Lock in a stable order so concurrent batches cannot deadlock.
            locked = Employee.objects.select_for_update().filter(
                pk__in=[employee.pk for employee in employees]
            )
            for employee in locked.order_by("pk"):
                item = AttendanceBatchItem.objects.create(batch=batch, employee=employee)
                item.batch = batch
                process_item(item, exception_flags=flags)
    except IntegrityError:
        # Most likely a concurrent request with the same event_id committed first.
        existing = AttendanceBatch.objects.filter(idempotency_key=event.event_id).first()
        if existing is None:
            raise
        return _replay(existing, actor=actor, event=event)

    return AttendanceResult(batch=batch_with_items(batch.pk), replayed=False)


# --- Authorisation ------------------------------------------------------------------


def _authorized_employees(actor: User, event: AttendanceEvent) -> list[Employee]:
    """Who this event may record attendance for. Raises if the actor may not record it."""
    if not event.is_group:
        if not has_capability(actor, Capability.ATTENDANCE_RECORD_SELF):
            raise AttendanceForbiddenError(
                "Your role cannot record attendance.", code="attendance_not_allowed"
            )
        employee = employee_for_user(actor)
        if employee is None:
            raise AttendanceForbiddenError(
                "Your account is not linked to an employee record.", code="no_employee_profile"
            )
        return [employee]

    if not has_any_capability(
        actor, Capability.ATTENDANCE_RECORD_ANY, Capability.ATTENDANCE_RECORD_CREW
    ):
        raise AttendanceForbiddenError(
            "Your role cannot record attendance for other employees.",
            code="group_attendance_not_allowed",
        )
    if not can_record_attendance_for_others(actor, event.job):
        raise AttendanceForbiddenError(
            f"You are not the LeadHand of job {event.job.job_number}, "
            "or you are not actively assigned to it.",
            code="not_job_lead_hand",
        )
    return list(event.employees)


def _is_admin_entry(actor: User, employees: list[Employee]) -> bool:
    """A company-wide user recording attendance for anyone other than themselves."""
    if not has_capability(actor, Capability.ATTENDANCE_RECORD_ANY):
        return False
    own = employee_for_user(actor)
    return any(own is None or employee.pk != own.pk for employee in employees)


def _require_current_admin_entry(event: AttendanceEvent, received_at: datetime) -> None:
    """Administrative entries must describe *now*, not the past.

    Backdated attendance belongs to the future correction workflow, which will
    record the original values, the change and its reason. Until then an Admin
    or Manager cannot use their company-wide access to enter past times.
    """
    max_age = timedelta(seconds=settings.ATTENDANCE_ADMIN_ENTRY_MAX_AGE_SECONDS)
    if received_at - event.captured_at > max_age:
        raise AdminEntryNotCurrentError(
            "Administrative attendance must be recorded at the time it happens. "
            "Past times will be handled by the correction workflow.",
            details={"max_age_seconds": settings.ATTENDANCE_ADMIN_ENTRY_MAX_AGE_SECONDS},
        )


# --- Idempotent replay -----------------------------------------------------------


def _replay(batch: AttendanceBatch, *, actor: User, event: AttendanceEvent) -> AttendanceResult:
    if batch.performed_by_id != actor.pk:
        # Do not reveal anything about another user's event.
        raise IdempotencyConflictError("This event_id has already been used.")

    batch = batch_with_items(batch.pk)
    if event.is_group:
        expected_employees = {employee.pk for employee in event.employees}
    else:
        own = employee_for_user(actor)
        expected_employees = {own.pk} if own else set()
    same_event = (
        batch.job_id == event.job.pk
        and batch.action_type == event.action_type
        and batch.captured_at == event.captured_at
        and {item.employee_id for item in batch.items.all()} == expected_employees
    )
    if not same_event:
        raise IdempotencyConflictError(
            "This event_id was already used for a different attendance event.",
            details={"batch_id": batch.pk},
        )
    return AttendanceResult(batch=batch, replayed=True)


# --- Batch creation ------------------------------------------------------------------


def _location_assessment(event: AttendanceEvent) -> LocationAssessment:
    geofence = build_job_geofence(
        latitude=event.job.latitude,
        longitude=event.job.longitude,
        radius_meters=event.job.geofence_radius_meters,
    )
    return assess_punch_location(
        latitude=event.latitude,
        longitude=event.longitude,
        accuracy_meters=event.accuracy_meters,
        geofence=geofence,
    )


def _create_batch(
    *,
    actor: User,
    event: AttendanceEvent,
    source: str,
    assessment: LocationAssessment,
    received_at: datetime,
) -> AttendanceBatch:
    coordinates = assessment.coordinates
    return AttendanceBatch.objects.create(
        idempotency_key=event.event_id,
        job=event.job,
        performed_by=actor,
        action_type=PunchType(event.action_type),
        source=source,
        captured_at=event.captured_at,
        received_at=received_at,
        entry_reason=event.reason,
        latitude=coordinates.latitude if coordinates else None,
        longitude=coordinates.longitude if coordinates else None,
        accuracy_meters=assessment.accuracy_meters,
        distance_meters=assessment.distance_meters,
        location_status=assessment.status,
        location_flags=list(assessment.flags),
    )


def _batch_exception_flags(batch: AttendanceBatch, assessment: LocationAssessment) -> list[str]:
    """Review reasons that apply to every employee in the batch.

    Administrative entries are often made away from the site (e.g. an office),
    so their location is stored for reference but never flags the session.
    """
    flags = []
    if batch.source != BatchSource.ADMIN_ENTRY:
        flags = [SessionExceptionFlag(flag.value) for flag in assessment.review_flags]
    tolerance = timedelta(seconds=settings.ATTENDANCE_FUTURE_TOLERANCE_SECONDS)
    if batch.captured_at > batch.received_at + tolerance:
        flags.append(SessionExceptionFlag.FUTURE_TIMESTAMP)
    return flags
