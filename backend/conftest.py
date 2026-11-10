import itertools
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User

DEFAULT_PASSWORD = "s3cure-Passw0rd"

_sequence = itertools.count(1)


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def make_user(db):
    def _make_user(
        email: str | None = None,
        password: str = DEFAULT_PASSWORD,
        role: str = Role.WORKER,
    ) -> User:
        email = email or f"user{next(_sequence)}@example.com"
        return User.objects.create_user(email=email, password=password, role=role)

    return _make_user


@pytest.fixture
def make_employee(db, make_user):
    from apps.workforce.models import Employee

    def _make_employee(*, role: str | None = Role.WORKER, **fields) -> Employee:
        """role=None creates an employee without a user account."""
        if "user" not in fields and role is not None:
            fields["user"] = make_user(role=role)
        fields.setdefault("name", f"Employee {next(_sequence)}")
        fields.setdefault("hourly_rate", Decimal("25.00"))
        return Employee.objects.create(**fields)

    return _make_employee


@pytest.fixture
def make_job(db, make_user):
    from apps.jobs.models import Job

    def _make_job(**fields) -> Job:
        fields.setdefault("job_number", f"J-{next(_sequence):04d}")
        fields.setdefault("name", "Test job")
        fields.setdefault("created_by", make_user(role=Role.ADMIN))
        return Job.objects.create(**fields)

    return _make_job


@pytest.fixture
def make_assignment(db, make_employee, make_job):
    from apps.jobs.models import JobAssignment

    def _make_assignment(**fields) -> JobAssignment:
        # Create defaults only when missing (setdefault would build them eagerly).
        if "employee" not in fields:
            fields["employee"] = make_employee()
        if "job" not in fields:
            fields["job"] = make_job()
        fields.setdefault("assigned_by", fields["job"].created_by)
        return JobAssignment.objects.create(**fields)

    return _make_assignment


@pytest.fixture
def make_batch(db):
    from apps.timekeeping.models import AttendanceBatch, BatchSource, LocationStatus, PunchType

    def _make_batch(*, job, performed_by, **fields) -> AttendanceBatch:
        fields.setdefault("idempotency_key", uuid.uuid4())
        fields.setdefault("action_type", PunchType.CLOCK_IN)
        fields.setdefault("source", BatchSource.MOBILE_ONLINE)
        fields.setdefault("captured_at", timezone.now())
        fields.setdefault("location_status", LocationStatus.LOCATION_UNAVAILABLE)
        return AttendanceBatch.objects.create(job=job, performed_by=performed_by, **fields)

    return _make_batch
