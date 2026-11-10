"""Request validation and response shapes for timekeeping. No business rules here."""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers

from apps.jobs.models import Job
from apps.timekeeping.models import (
    AttendanceBatch,
    AttendanceBatchItem,
    BatchSource,
    PunchType,
    ReviewDecision,
    ReviewStatus,
    SessionStatus,
    WorkSession,
    WorkSessionReview,
)
from apps.timekeeping.services.attendance import AttendanceEvent
from apps.timekeeping.services.location_validation import flags_require_review
from apps.workforce.models import Employee

# --- Input fields ------------------------------------------------------------------


class AwareDateTimeField(serializers.DateTimeField):
    """An ISO 8601 datetime that must carry a UTC offset.

    A naive device time cannot be placed on the timeline reliably, so it is a
    structural error rather than something to guess.
    """

    default_error_messages = {
        "naive": "Include a UTC offset, for example 2026-11-06T08:00:00-05:00.",
    }

    def to_internal_value(self, value):
        if isinstance(value, str):
            try:
                parsed = parse_datetime(value.strip())
            except ValueError:
                parsed = None
            if parsed is not None and timezone.is_naive(parsed):
                self.fail("naive")
        return super().to_internal_value(value)


class RawValueField(serializers.Field):
    """Passes the value through untouched.

    Used for location data: malformed GPS values must reach the location
    assessor (which discards and flags them) instead of failing validation.
    """

    def to_internal_value(self, data):
        return data

    def to_representation(self, value):
        return value


# --- Event payloads ------------------------------------------------------------------


class _EventSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    job_id = serializers.PrimaryKeyRelatedField(queryset=Job.objects.all(), source="job")
    captured_at = AwareDateTimeField()
    location = RawValueField(required=False, allow_null=True, default=None)

    def to_event(self, *, action_type: str, employees=None) -> AttendanceEvent:
        data = self.validated_data
        latitude, longitude, accuracy = _location_parts(data.get("location"))
        return AttendanceEvent(
            event_id=data["event_id"],
            action_type=action_type,
            job=data["job"],
            captured_at=data["captured_at"],
            employees=tuple(employees) if employees is not None else None,
            latitude=latitude,
            longitude=longitude,
            accuracy_meters=accuracy,
            reason=data.get("reason", ""),
        )


class _EmployeeIdsMixin(serializers.Serializer):
    # Optional note for entries made on behalf of others (e.g. administrative entries).
    reason = serializers.CharField(
        required=False, allow_blank=True, max_length=500, trim_whitespace=True
    )
    employee_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=settings.ATTENDANCE_MAX_GROUP_SIZE,
    )

    def validate_employee_ids(self, ids: list[int]) -> list[Employee]:
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError("Employee ids must be unique.")
        employees = {employee.pk: employee for employee in Employee.objects.filter(pk__in=ids)}
        missing = [pk for pk in ids if pk not in employees]
        if missing:
            raise serializers.ValidationError(f"Unknown employee ids: {missing}.")
        return [employees[pk] for pk in ids]


class SelfPunchSerializer(_EventSerializer):
    """Individual clock-in/out. The employee comes from the authenticated user."""


class GroupPunchSerializer(_EmployeeIdsMixin, _EventSerializer):
    def to_event(self, *, action_type: str, employees=None) -> AttendanceEvent:
        return super().to_event(
            action_type=action_type, employees=self.validated_data["employee_ids"]
        )


class SyncEventSerializer(_EmployeeIdsMixin, _EventSerializer):
    """One queued offline event. Omit ``employee_ids`` for a self punch."""

    action_type = serializers.ChoiceField(choices=PunchType.choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee_ids"].required = False

    def to_event(self, *, action_type: str | None = None, employees=None) -> AttendanceEvent:
        return super().to_event(
            action_type=self.validated_data["action_type"],
            employees=self.validated_data.get("employee_ids"),
        )


class SyncRequestSerializer(serializers.Serializer):
    # Each element is validated separately so one malformed event cannot
    # reject the whole submission.
    events = serializers.ListField(
        child=RawValueField(),
        allow_empty=False,
        max_length=settings.ATTENDANCE_MAX_SYNC_EVENTS,
    )


def _location_parts(location) -> tuple[object, object, object]:
    if location is None:
        return None, None, None
    if isinstance(location, dict):
        return location.get("latitude"), location.get("longitude"), location.get("accuracy_meters")
    # Not an object: unusable coordinates, flagged invalid_coordinates.
    return location, location, None


# --- Shared output pieces ------------------------------------------------------------


def _job(job: Job) -> dict:
    return {"id": job.pk, "job_number": job.job_number, "name": job.name}


def _employee(employee: Employee) -> dict:
    return {"id": employee.pk, "name": employee.name}


def _user(user) -> dict | None:
    return {"id": user.pk, "email": user.email} if user else None


def _location(batch: AttendanceBatch) -> dict:
    return {
        "status": batch.location_status,
        "flags": list(batch.location_flags),
        # Administrative entries keep their location for reference only (ADR 011).
        "requires_review": batch.source != BatchSource.ADMIN_ENTRY
        and flags_require_review(batch.location_flags),
        "latitude": _decimal(batch.latitude),
        "longitude": _decimal(batch.longitude),
        "accuracy_meters": _decimal(batch.accuracy_meters),
        "distance_meters": _decimal(batch.distance_meters),
    }


def _decimal(value) -> str | None:
    return None if value is None else str(value)


def _datetime(value) -> str | None:
    return None if value is None else serializers.DateTimeField().to_representation(value)


# --- Attendance batch result ---------------------------------------------------------


def item_result_data(item: AttendanceBatchItem) -> dict:
    punch = getattr(item, "time_punch", None)
    return {
        "employee": _employee(item.employee),
        "status": item.result_status,
        "code": item.result_code,
        "message": item.result_message,
        "session_id": punch.session_id if punch else None,
        "punch_id": punch.pk if punch else None,
        "processed_at": _datetime(item.processed_at),
    }


def batch_result_data(batch: AttendanceBatch, *, replayed: bool) -> dict:
    """The full outcome of an attendance event, built only from stored data,
    so the first response and every retry are identical (apart from ``replayed``)."""
    return {
        "event_id": str(batch.idempotency_key),
        "batch_id": batch.pk,
        "action_type": batch.action_type,
        "source": batch.source,
        "job": _job(batch.job),
        "performed_by": _user(batch.performed_by),
        "captured_at": _datetime(batch.captured_at),
        "received_at": _datetime(batch.received_at),
        "entry_reason": batch.entry_reason,
        "location": _location(batch),
        "results": [item_result_data(item) for item in batch.items.all()],
        "replayed": replayed,
    }


# --- Sessions ------------------------------------------------------------------------


def _punch_data(punch) -> dict | None:
    if punch is None:
        return None
    batch = punch.batch_item.batch
    return {
        "punch_id": punch.pk,
        "at": _datetime(batch.captured_at),
        "received_at": _datetime(batch.received_at),
        "event_id": str(batch.idempotency_key),
        "source": batch.source,
        "performed_by": _user(batch.performed_by),
        "location": _location(batch),
    }


class WorkSessionSerializer(serializers.ModelSerializer):
    employee = serializers.SerializerMethodField()
    job = serializers.SerializerMethodField()
    clock_in = serializers.SerializerMethodField()
    clock_out = serializers.SerializerMethodField()
    duration_seconds = serializers.SerializerMethodField()
    reviewed_by = serializers.SerializerMethodField()

    class Meta:
        model = WorkSession
        fields = (
            "id",
            "employee",
            "job",
            "work_date",
            "session_status",
            "review_status",
            "exception_flags",
            "clock_in",
            "clock_out",
            "duration_seconds",
            "reviewed_by",
            "reviewed_at",
        )
        read_only_fields = fields

    def _punch(self, session: WorkSession, punch_type: str):
        return next((p for p in session.punches.all() if p.punch_type == punch_type), None)

    def get_employee(self, session):
        return _employee(session.assignment.employee)

    def get_job(self, session):
        return _job(session.assignment.job)

    def get_clock_in(self, session):
        return _punch_data(self._punch(session, PunchType.CLOCK_IN))

    def get_clock_out(self, session):
        return _punch_data(self._punch(session, PunchType.CLOCK_OUT))

    def get_duration_seconds(self, session) -> int | None:
        start, end = getattr(session, "clock_in_at", None), getattr(session, "clock_out_at", None)
        if start is None or end is None:
            return None
        return int((end - start).total_seconds())

    def get_reviewed_by(self, session):
        return _user(session.reviewed_by)


class WorkSessionReviewSerializer(serializers.ModelSerializer):
    reviewed_by = serializers.SerializerMethodField()

    class Meta:
        model = WorkSessionReview
        fields = ("id", "decision", "reason", "reviewed_by", "reviewed_at")
        read_only_fields = fields

    def get_reviewed_by(self, review):
        return _user(review.reviewed_by)


class StaffWorkSessionSerializer(WorkSessionSerializer):
    reviews = WorkSessionReviewSerializer(many=True, read_only=True)

    class Meta(WorkSessionSerializer.Meta):
        fields = (*WorkSessionSerializer.Meta.fields, "reviews")
        read_only_fields = fields


class RejectedEventSerializer(serializers.ModelSerializer):
    """A rejected attendance item: a synchronisation exception for reviewers."""

    event_id = serializers.UUIDField(source="batch.idempotency_key")
    action_type = serializers.CharField(source="batch.action_type")
    source = serializers.CharField(source="batch.source")
    job = serializers.SerializerMethodField()
    employee = serializers.SerializerMethodField()
    performed_by = serializers.SerializerMethodField()
    captured_at = serializers.DateTimeField(source="batch.captured_at")
    received_at = serializers.DateTimeField(source="batch.received_at")
    code = serializers.CharField(source="result_code")
    message = serializers.CharField(source="result_message")

    class Meta:
        model = AttendanceBatchItem
        fields = (
            "id",
            "event_id",
            "action_type",
            "source",
            "job",
            "employee",
            "performed_by",
            "captured_at",
            "received_at",
            "code",
            "message",
        )
        read_only_fields = fields

    def get_job(self, item):
        return _job(item.batch.job)

    def get_employee(self, item):
        return _employee(item.employee)

    def get_performed_by(self, item):
        return _user(item.batch.performed_by)


# --- Query parameters and review input ---------------------------------------------


class SessionFilterSerializer(serializers.Serializer):
    work_date_from = serializers.DateField(required=False)
    work_date_to = serializers.DateField(required=False)
    job_id = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        start, end = attrs.get("work_date_from"), attrs.get("work_date_to")
        if start and end and end < start:
            raise serializers.ValidationError(
                {"work_date_to": "Must not be before work_date_from."}
            )
        return attrs


class StaffSessionFilterSerializer(SessionFilterSerializer):
    employee_id = serializers.IntegerField(required=False, min_value=1)
    review_status = serializers.ChoiceField(choices=ReviewStatus.choices, required=False)
    session_status = serializers.ChoiceField(choices=SessionStatus.choices, required=False)


class RejectedEventFilterSerializer(serializers.Serializer):
    job_id = serializers.IntegerField(required=False, min_value=1)
    employee_id = serializers.IntegerField(required=False, min_value=1)


class ReviewInputSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=ReviewDecision.choices)
    reason = serializers.CharField(max_length=2000, trim_whitespace=True)


# --- Status and crew ------------------------------------------------------------------


def crew_member_data(member: dict) -> dict:
    employee, session = member["employee"], member["open_session"]
    return {
        "employee": {**_employee(employee), "has_account": employee.user_id is not None},
        "assignment_id": member["assignment"].pk,
        "clocked_in": session is not None,
        "open_session": None
        if session is None
        else {
            "id": session.pk,
            "job": _job(session.assignment.job),
            "clock_in_at": _datetime(session.clock_in_at),
        },
    }
