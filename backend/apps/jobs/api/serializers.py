"""Request validation and response shapes for jobs and assignments. No business rules."""

from __future__ import annotations

from django.conf import settings
from rest_framework import serializers

from apps.jobs.models import AssignmentStatus, Job, JobAssignment, JobStatus
from apps.workforce.models import Employee


class _StrictSerializer(serializers.Serializer):
    """Rejects unknown fields instead of silently ignoring them."""

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = sorted(set(data) - set(self.fields))
            if unknown:
                raise serializers.ValidationError({field: ["Unknown field."] for field in unknown})
        return super().to_internal_value(data)


class EmptyBodySerializer(_StrictSerializer):
    """For action endpoints that take no fields."""


# --- Jobs: input ------------------------------------------------------------------------


class _JobFieldsSerializer(_StrictSerializer):
    job_number = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=200)
    address = serializers.CharField(max_length=300, allow_blank=True, required=False)
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=-90, max_value=90, allow_null=True, required=False
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=-180,
        max_value=180,
        allow_null=True,
        required=False,
    )
    geofence_radius_meters = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    start_date = serializers.DateField(allow_null=True, required=False)
    end_date = serializers.DateField(allow_null=True, required=False)
    status = serializers.ChoiceField(choices=JobStatus.choices, required=False)

    def validate(self, attrs):
        job = self.instance
        merged = {
            field: attrs[field] if field in attrs else getattr(job, field, None)
            for field in ("latitude", "longitude", "start_date", "end_date")
        }
        if (merged["latitude"] is None) != (merged["longitude"] is None):
            raise serializers.ValidationError(
                {"latitude": ["Latitude and longitude must be set together, or both left empty."]}
            )
        if (
            merged["start_date"]
            and merged["end_date"]
            and merged["end_date"] < merged["start_date"]
        ):
            raise serializers.ValidationError({"end_date": ["Must not be before start_date."]})
        return attrs


class JobCreateSerializer(_JobFieldsSerializer):
    lead_hand_id = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(), allow_null=True, required=False
    )


class JobUpdateSerializer(_JobFieldsSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False


class LeadHandSerializer(_StrictSerializer):
    employee_id = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(), allow_null=True
    )


class JobFilterSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=JobStatus.choices, required=False)
    search = serializers.CharField(required=False, max_length=100)
    managed_by_me = serializers.BooleanField(required=False, default=False)
    assigned_to_me = serializers.BooleanField(required=False, default=False)


# --- Assignments: input ---------------------------------------------------------------


class _DatesMixin(serializers.Serializer):
    def validate(self, attrs):
        assignment = self.instance
        start = attrs.get("start_date", getattr(assignment, "start_date", None))
        end = attrs.get("end_date", getattr(assignment, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": ["Must not be before start_date."]})
        return attrs


class AssignEmployeesSerializer(_DatesMixin, _StrictSerializer):
    employee_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=settings.ATTENDANCE_MAX_GROUP_SIZE,
    )
    start_date = serializers.DateField(allow_null=True, required=False)
    end_date = serializers.DateField(allow_null=True, required=False)

    def validate_employee_ids(self, ids: list[int]) -> list[Employee]:
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError("Employee ids must be unique.")
        employees = {employee.pk: employee for employee in Employee.objects.filter(pk__in=ids)}
        missing = [pk for pk in ids if pk not in employees]
        if missing:
            raise serializers.ValidationError(f"Unknown employee ids: {missing}.")
        return [employees[pk] for pk in ids]


class AssignmentDatesSerializer(_DatesMixin, _StrictSerializer):
    start_date = serializers.DateField(allow_null=True, required=False)
    end_date = serializers.DateField(allow_null=True, required=False)


class EndAssignmentSerializer(_StrictSerializer):
    end_date = serializers.DateField(required=False)


class AssignmentFilterSerializer(serializers.Serializer):
    job_id = serializers.IntegerField(required=False, min_value=1)
    employee_id = serializers.IntegerField(required=False, min_value=1)
    # "all" includes the history (ended and cancelled).
    status = serializers.ChoiceField(
        choices=[*AssignmentStatus.values, "all"], required=False, default=AssignmentStatus.ACTIVE
    )

    def validate_status(self, value):
        return None if value == "all" else value


# --- Output ----------------------------------------------------------------------------


def _decimal(value) -> str | None:
    return None if value is None else str(value)


def _datetime(value) -> str | None:
    return None if value is None else serializers.DateTimeField().to_representation(value)


def _date(value) -> str | None:
    return None if value is None else value.isoformat()


def _person(user) -> dict | None:
    """A user shown by name only; emails are not exposed in job data."""
    if user is None:
        return None
    employee = getattr(user, "employee", None)
    name = user.get_full_name() or (employee.name if employee else "")
    return {"id": user.pk, "name": name}


def job_data(job: Job, viewer: dict) -> dict:
    configured = job.latitude is not None and job.longitude is not None
    return {
        "id": job.pk,
        "job_number": job.job_number,
        "name": job.name,
        "address": job.address,
        "status": job.status,
        "start_date": _date(job.start_date),
        "end_date": _date(job.end_date),
        "geofence": {
            "configured": configured,
            "latitude": _decimal(job.latitude),
            "longitude": _decimal(job.longitude),
            "radius_meters": job.geofence_radius_meters,
        },
        "lead_hand": None
        if job.lead_hand_id is None
        else {"employee_id": job.lead_hand_id, "name": job.lead_hand.name},
        "viewer": {
            "manages_job": job.pk in viewer["managed_job_ids"],
            "is_lead_hand": job.lead_hand_id is not None
            and job.lead_hand_id == viewer["my_employee_id"],
            "my_assignment_id": viewer["my_assignment_ids"].get(job.pk),
        },
        "created_by": _person(job.created_by),
        "updated_by": _person(job.updated_by),
        "created_at": _datetime(job.created_at),
        "updated_at": _datetime(job.updated_at),
    }


def assignment_data(assignment: JobAssignment) -> dict:
    employee, job = assignment.employee, assignment.job
    return {
        "id": assignment.pk,
        "job": {"id": job.pk, "job_number": job.job_number, "name": job.name},
        "employee": {
            "id": employee.pk,
            "name": employee.name,
            "employee_number": employee.employee_number,
            "has_account": employee.user_id is not None,
        },
        "status": assignment.status,
        "start_date": _date(assignment.start_date),
        "end_date": _date(assignment.end_date),
        "is_lead_hand": job.lead_hand_id == employee.pk,
        "assigned_at": _datetime(assignment.assigned_at),
        "assigned_by": _person(assignment.assigned_by),
        "updated_at": _datetime(assignment.updated_at),
    }
