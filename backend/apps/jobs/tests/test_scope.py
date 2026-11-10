"""Shared job and crew scope (apps/jobs/selectors/scope.py)."""

import pytest

from apps.accounts.models import Role
from apps.jobs.models import AssignmentStatus
from apps.jobs.selectors.scope import (
    assigned_jobs,
    assignments_visible_to,
    attendance_jobs_for,
    can_record_attendance_for_others,
    can_view_crew,
    crew_assignments,
    jobs_editable_by,
    jobs_visible_to,
    managed_jobs,
    manages_job,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def leadhand(make_employee):
    return make_employee(role=Role.LEADHAND)


def test_leadhand_manages_a_job_only_when_lead_and_actively_assigned(
    leadhand, make_job, make_assignment
):
    both = make_job(lead_hand=leadhand)
    make_assignment(employee=leadhand, job=both)
    lead_only = make_job(lead_hand=leadhand)
    assigned_only = make_job()
    make_assignment(employee=leadhand, job=assigned_only)
    ended = make_job(lead_hand=leadhand)
    make_assignment(employee=leadhand, job=ended, status=AssignmentStatus.ENDED)

    assert list(managed_jobs(leadhand.user)) == [both]
    assert manages_job(leadhand.user, both)
    assert not manages_job(leadhand.user, lead_only)
    assert not manages_job(leadhand.user, assigned_only)
    assert not manages_job(leadhand.user, ended)


def test_crew_is_everyone_actively_assigned_to_managed_jobs(
    leadhand, make_employee, make_job, make_assignment
):
    job = make_job(lead_hand=leadhand)
    make_assignment(employee=leadhand, job=job)
    member = make_employee()
    make_assignment(employee=member, job=job)
    make_assignment(employee=make_employee(), job=job, status=AssignmentStatus.ENDED)
    outsider_job = make_job()
    make_assignment(employee=make_employee(), job=outsider_job)

    crew = {assignment.employee for assignment in crew_assignments(leadhand.user)}

    assert crew == {leadhand, member}


@pytest.mark.parametrize("role", [Role.ADMIN, Role.MANAGER, Role.WORKER])
def test_only_leadhands_manage_jobs(make_employee, make_job, make_assignment, role):
    user_employee = make_employee(role=role)
    job = make_job(lead_hand=user_employee)  # even if (wrongly) named as lead_hand
    make_assignment(employee=user_employee, job=job)

    assert not managed_jobs(user_employee.user).exists()


def test_job_visibility(make_employee, make_job, make_assignment):
    worker = make_employee(role=Role.WORKER)
    mine, other = make_job(), make_job()
    make_assignment(employee=worker, job=mine)
    manager = make_employee(role=Role.MANAGER)

    assert list(assigned_jobs(worker.user)) == [mine]
    assert list(jobs_visible_to(worker.user)) == [mine]
    assert set(jobs_visible_to(manager.user)) == {mine, other}


def test_attendance_scope(leadhand, make_employee, make_job, make_assignment):
    job = make_job(lead_hand=leadhand)
    make_assignment(employee=leadhand, job=job)

    assert attendance_jobs_for(make_employee(role=Role.MANAGER).user) is None  # company-wide
    assert list(attendance_jobs_for(leadhand.user)) == [job]
    assert not attendance_jobs_for(make_employee(role=Role.WORKER).user).exists()


def test_who_may_record_attendance_for_others(leadhand, make_employee, make_job, make_assignment):
    managed = make_job(lead_hand=leadhand)
    make_assignment(employee=leadhand, job=managed)
    unrelated = make_job()

    assert can_record_attendance_for_others(leadhand.user, managed)
    assert not can_record_attendance_for_others(leadhand.user, unrelated)
    for role in (Role.ADMIN, Role.MANAGER):
        assert can_record_attendance_for_others(make_employee(role=role).user, unrelated)
    assert not can_record_attendance_for_others(make_employee(role=Role.WORKER).user, managed)


def test_jobs_editable_by_role(leadhand, make_employee, make_job, make_assignment):
    managed = make_job(lead_hand=leadhand)
    make_assignment(employee=leadhand, job=managed)
    crew_only = make_job()
    make_assignment(employee=leadhand, job=crew_only)

    assert list(jobs_editable_by(leadhand.user)) == [managed]
    assert jobs_editable_by(make_employee(role=Role.MANAGER).user).count() == 2
    assert not jobs_editable_by(make_employee(role=Role.WORKER).user).exists()


def test_can_view_crew(leadhand, make_employee, make_job, make_assignment):
    managed = make_job(lead_hand=leadhand)
    make_assignment(employee=leadhand, job=managed)
    other = make_job()
    worker = make_employee(role=Role.WORKER)
    make_assignment(employee=worker, job=managed)

    assert can_view_crew(leadhand.user, managed)
    assert not can_view_crew(leadhand.user, other)
    assert not can_view_crew(worker.user, managed)  # employees never see the crew
    assert can_view_crew(make_employee(role=Role.ADMIN).user, other)


def test_assignments_visible_to(leadhand, make_employee, make_job, make_assignment):
    managed = make_job(lead_hand=leadhand)
    lead_row = make_assignment(employee=leadhand, job=managed)
    worker = make_employee(role=Role.WORKER)
    worker_row = make_assignment(employee=worker, job=managed)
    ended_row = make_assignment(
        employee=make_employee(), job=managed, status=AssignmentStatus.ENDED
    )
    elsewhere = make_assignment(employee=make_employee(), job=make_job())

    assert set(assignments_visible_to(leadhand.user)) == {lead_row, worker_row, ended_row}
    assert list(assignments_visible_to(worker.user)) == [worker_row]
    assert set(assignments_visible_to(make_employee(role=Role.MANAGER).user)) == {
        lead_row,
        worker_row,
        ended_row,
        elsewhere,
    }
