from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.accounts.models import Role
from apps.jobs.models import AssignmentStatus

pytestmark = pytest.mark.django_db


# --- Job ---------------------------------------------------------------------------


def test_job_without_geofence_is_valid_and_keeps_default_radius(make_job):
    job = make_job()

    assert job.latitude is None
    assert job.longitude is None
    assert job.geofence_radius_meters == 100


def test_job_radius_is_customisable(make_job):
    job = make_job(
        latitude=Decimal("43.6426"), longitude=Decimal("-79.3871"), geofence_radius_meters=250
    )

    assert job.geofence_radius_meters == 250


@pytest.mark.parametrize(
    "fields",
    [
        {"latitude": Decimal("43.6426")},  # longitude missing
        {"longitude": Decimal("-79.3871")},  # latitude missing
        {"latitude": Decimal("91"), "longitude": Decimal("0")},
        {"latitude": Decimal("0"), "longitude": Decimal("-181")},
        {"geofence_radius_meters": 0},
        {"start_date": date(2026, 5, 2), "end_date": date(2026, 5, 1)},
    ],
)
def test_job_integrity_constraints(make_job, fields):
    with pytest.raises(IntegrityError):
        make_job(**fields)


def test_job_number_is_unique(make_job):
    make_job(job_number="J-1")

    with pytest.raises(IntegrityError):
        make_job(job_number="J-1")


def test_job_lead_hand_is_optional(make_job):
    assert make_job().lead_hand is None


def test_job_lead_hand_must_be_a_leadhand_user(make_job, make_employee):
    leadhand = make_employee(role=Role.LEADHAND)
    worker = make_employee(role=Role.WORKER)
    no_account = make_employee(role=None)

    make_job(lead_hand=leadhand).full_clean()
    for employee in (worker, no_account):
        job = make_job(lead_hand=employee)
        with pytest.raises(ValidationError) as exc_info:
            job.full_clean()
        assert "lead_hand" in exc_info.value.message_dict


# --- JobAssignment -------------------------------------------------------------------


def test_employee_can_be_assigned_to_many_jobs_and_job_to_many_employees(
    make_assignment, make_employee, make_job
):
    employee, job = make_employee(), make_job()
    make_assignment(employee=employee)
    make_assignment(employee=employee, job=job)
    make_assignment(job=job)

    assert employee.job_assignments.count() == 2
    assert job.assignments.count() == 2


def test_only_one_active_assignment_per_employee_and_job(make_assignment):
    first = make_assignment()

    with pytest.raises(IntegrityError):
        make_assignment(employee=first.employee, job=first.job)


def test_ended_assignments_do_not_block_reassignment(make_assignment):
    first = make_assignment(status=AssignmentStatus.ENDED)

    make_assignment(employee=first.employee, job=first.job)


def test_assignment_dates_must_be_ordered(make_assignment):
    with pytest.raises(IntegrityError):
        make_assignment(start_date=date(2026, 5, 2), end_date=date(2026, 5, 1))
