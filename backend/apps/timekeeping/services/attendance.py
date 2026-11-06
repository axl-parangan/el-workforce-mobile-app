"""Record an attendance event: the single entry point for every punch.

Online clock-in/out, LeadHand group clock-in/out and offline sync all call
``record_attendance``. One event becomes one AttendanceBatch with one item per
employee (ADR 003, 006).

Idempotency (ADR 002): the client-generated ``event_id`` is stored as
``AttendanceBatch.idempotency_key`` (unique). Re-sending an event returns the
stored batch and its items unchanged. A concurrent duplicate blocks on the
unique index until the first transaction commits, then replays its result.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status

from apps.accounts.models import Role, User
from apps.jobs.models import Job
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

    assessment = _location_assessment(event)
    try:
        with transaction.atomic():
            batch = _create_batch(actor=actor, event=event, source=source, assessment=assessment)
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
    if not event.is_group:
        employee = employee_for_user(actor)
        if employee is None:
            raise AttendanceForbiddenError(
                "Your account is not linked to an employee record.", code="no_employee_profile"
            )
        return [employee]

    if actor.role != Role.LEADHAND:
        raise AttendanceForbiddenError(
            "Only LeadHands can record attendance for other employees.",
            code="leadhand_role_required",
        )
    actor_employee = employee_for_user(actor)
    if actor_employee is None or event.job.lead_hand_id != actor_employee.pk:
        raise AttendanceForbiddenError(
            f"You are not the LeadHand of job {event.job.job_number}.",
            code="not_job_lead_hand",
        )
    return list(event.employees)


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
    *, actor: User, event: AttendanceEvent, source: str, assessment: LocationAssessment
) -> AttendanceBatch:
    coordinates = assessment.coordinates
    return AttendanceBatch.objects.create(
        idempotency_key=event.event_id,
        job=event.job,
        performed_by=actor,
        action_type=PunchType(event.action_type),
        source=source,
        captured_at=event.captured_at,
        received_at=timezone.now(),
        latitude=coordinates.latitude if coordinates else None,
        longitude=coordinates.longitude if coordinates else None,
        accuracy_meters=assessment.accuracy_meters,
        distance_meters=assessment.distance_meters,
        location_status=assessment.status,
        location_flags=list(assessment.flags),
    )


def _batch_exception_flags(batch: AttendanceBatch, assessment: LocationAssessment) -> list[str]:
    """Review reasons that apply to every employee in the batch."""
    flags = [SessionExceptionFlag(flag.value) for flag in assessment.review_flags]
    tolerance = timedelta(seconds=settings.ATTENDANCE_FUTURE_TOLERANCE_SECONDS)
    if batch.captured_at > batch.received_at + tolerance:
        flags.append(SessionExceptionFlag.FUTURE_TIMESTAMP)
    return flags
