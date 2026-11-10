"""Assignments API: bulk assign, visibility, lifecycle and history."""

import threading
from datetime import date, timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apps.accounts.models import Role
from apps.jobs.models import AssignmentStatus, JobAssignment, JobStatus
from apps.timekeeping.models import WorkSession
from common.timezones import work_date_for

from .conftest import url

pytestmark = pytest.mark.django_db


def today() -> date:
    return work_date_for(timezone.now())


@pytest.fixture
def crew(make_employee):
    return [make_employee(role=Role.WORKER, name=n) for n in ("Ana", "Ben")]


def assign(client, job, employees, **extra):
    return client.post(
        url("jobs:assignments", pk=job.pk),
        {"employee_ids": [e.pk for e in employees], **extra},
        format="json",
    )


def results_by_employee(response):
    return {r["employee_id"]: r for r in response.json()["results"]}


# --- Assigning ----------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_bulk_assign_with_individual_results(request, client_for, managed_job, crew, role):
    actor = request.getfixturevalue(role)

    response = assign(client_for(actor.user), managed_job, crew, start_date="2026-12-01")

    assert response.status_code == 201, response.json()
    results = results_by_employee(response)
    assert {r["code"] for r in results.values()} == {"assigned"}
    for employee in crew:
        assignment = JobAssignment.objects.get(employee=employee, job=managed_job)
        assert assignment.assigned_by == actor.user
        assert str(assignment.start_date) == "2026-12-01"
        assert results[employee.pk]["assignment"]["id"] == assignment.pk


def test_partial_success_reports_each_employee(
    client_for, manager, managed_job, crew, make_employee
):
    assign(client_for(manager.user), managed_job, crew[:1])
    inactive = make_employee(is_active=False)

    response = assign(client_for(manager.user), managed_job, [*crew, inactive])

    results = results_by_employee(response)
    assert results[crew[0].pk]["code"] == "already_assigned"
    assert results[crew[0].pk]["assignment"] is not None  # the existing assignment
    assert results[crew[1].pk]["code"] == "assigned"
    assert results[inactive.pk]["code"] == "employee_inactive"
    assert JobAssignment.objects.filter(employee=crew[0], job=managed_job).count() == 1


def test_employees_without_accounts_can_be_assigned(
    client_for, manager, managed_job, make_employee
):
    no_login = make_employee(role=None)

    response = assign(client_for(manager.user), managed_job, [no_login])

    assert results_by_employee(response)[no_login.pk]["code"] == "assigned"


@pytest.mark.parametrize("job_status", ["planned", "active", "on_hold"])
def test_planned_active_and_on_hold_jobs_accept_assignments(
    client_for, manager, make_job, crew, job_status
):
    job = make_job(status=job_status)

    assert (
        results_by_employee(assign(client_for(manager.user), job, crew))[crew[0].pk]["code"]
        == "assigned"
    )


@pytest.mark.parametrize("job_status", ["completed", "cancelled"])
def test_completed_and_cancelled_jobs_refuse_assignments(
    client_for, manager, make_job, crew, job_status
):
    job = make_job(status=job_status)

    response = assign(client_for(manager.user), job, crew)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "job_not_assignable"
    assert not JobAssignment.objects.filter(job=job).exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"employee_ids": []},
        {"employee_ids": [1, 1]},
        {"employee_ids": [999999]},
        {"employee_ids": "nope"},
    ],
)
def test_invalid_employee_lists(client_for, manager, managed_job, payload):
    response = client_for(manager.user).post(
        url("jobs:assignments", pk=managed_job.pk), payload, format="json"
    )

    assert response.status_code == 400
    assert "employee_ids" in response.json()["error"]["details"]


def test_assignment_dates_must_be_ordered(client_for, manager, managed_job, crew):
    response = assign(
        client_for(manager.user), managed_job, crew, start_date="2026-12-02", end_date="2026-12-01"
    )

    assert response.status_code == 400


@pytest.mark.parametrize("role", ["leadhand", "worker"])
def test_leadhands_and_employees_cannot_assign(request, client_for, managed_job, crew, role):
    response = assign(client_for(request.getfixturevalue(role).user), managed_job, crew)

    assert response.status_code == 403
    assert not JobAssignment.objects.filter(employee__in=crew).exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_assignment_creates_one_row(client_for, manager, managed_job, crew):
    barrier = threading.Barrier(2)
    responses = []

    def run():
        try:
            barrier.wait()
            responses.append(assign(client_for(manager.user), managed_job, crew[:1]))
        finally:
            connection.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    codes = sorted(r.json()["results"][0]["code"] for r in responses)
    assert codes == ["already_assigned", "assigned"]
    assert JobAssignment.objects.filter(employee=crew[0], job=managed_job).count() == 1


# --- Visibility ----------------------------------------------------------------------------


def test_job_crew_list_for_each_role(
    client_for, admin, manager, leadhand, worker, managed_job, other_job, make_assignment
):
    make_assignment(employee=worker, job=managed_job)

    for actor in (admin, manager, leadhand):
        body = client_for(actor.user).get(url("jobs:assignments", pk=managed_job.pk)).json()
        assert {a["employee"]["name"] for a in body["results"]} == {"Lee Lead", "Wendy Worker"}
    # Employees never see the crew list (Q9).
    assert (
        client_for(worker.user).get(url("jobs:assignments", pk=managed_job.pk)).status_code == 403
    )
    # A LeadHand cannot see another LeadHand's crew.
    assert (
        client_for(leadhand.user).get(url("jobs:assignments", pk=other_job.pk)).status_code == 404
    )


def test_crew_scoped_leadhand_sees_crew_history(
    client_for, leadhand, managed_job, make_assignment, worker
):
    make_assignment(employee=worker, job=managed_job, status=AssignmentStatus.ENDED)
    client = client_for(leadhand.user)

    active = client.get(url("jobs:assignments", pk=managed_job.pk)).json()
    history = client.get(url("jobs:assignments", pk=managed_job.pk), {"status": "all"}).json()

    assert active["count"] == 1
    assert history["count"] == 2


def test_assignment_list_scope_per_role(
    client_for, manager, leadhand, worker, managed_job, other_job, make_assignment
):
    mine = make_assignment(employee=worker, job=managed_job)

    assert client_for(manager.user).get(url("assignments:list")).json()["count"] == 4
    # LeadHand: their job's crew (themselves and the worker), not the other job.
    lead_ids = {
        a["id"] for a in client_for(leadhand.user).get(url("assignments:list")).json()["results"]
    }
    assert mine.pk in lead_ids
    assert not JobAssignment.objects.filter(pk__in=lead_ids, job=other_job).exists()
    # Employee: only their own.
    worker_body = client_for(worker.user).get(url("assignments:list")).json()
    assert [a["id"] for a in worker_body["results"]] == [mine.pk]


def test_employee_cannot_open_a_colleagues_assignment(
    client_for, worker, managed_job, make_assignment, make_employee
):
    make_assignment(employee=worker, job=managed_job)
    colleague = make_assignment(employee=make_employee(), job=managed_job)

    response = client_for(worker.user).get(url("assignments:detail", pk=colleague.pk))

    assert response.status_code == 404


def test_my_assignments(client_for, leadhand, worker, managed_job, other_job, make_assignment):
    make_assignment(employee=worker, job=managed_job)
    make_assignment(employee=leadhand, job=other_job, status=AssignmentStatus.ENDED)

    body = client_for(leadhand.user).get(url("assignments:mine")).json()
    history = client_for(leadhand.user).get(url("assignments:mine"), {"status": "all"}).json()

    assert [a["job"]["job_number"] for a in body["results"]] == ["J-100"]  # own only, not crew
    assert history["count"] == 2


def test_assignment_response_hides_pay(client_for, manager, managed_job, worker, make_assignment):
    assignment = make_assignment(employee=worker, job=managed_job)

    body = client_for(manager.user).get(url("assignments:detail", pk=assignment.pk)).json()

    assert body["employee"] == {
        "id": worker.pk,
        "name": "Wendy Worker",
        "employee_number": None,
        "has_account": True,
    }
    assert "hourly_rate" not in str(body)


# --- Changing dates -------------------------------------------------------------------------


def test_manager_changes_assignment_dates(
    client_for, manager, managed_job, worker, make_assignment
):
    assignment = make_assignment(employee=worker, job=managed_job, start_date=date(2026, 12, 1))

    response = client_for(manager.user).patch(
        url("assignments:detail", pk=assignment.pk), {"end_date": "2026-12-31"}, format="json"
    )

    assert response.status_code == 200, response.json()
    assignment.refresh_from_db()
    assert str(assignment.start_date) == "2026-12-01"
    assert str(assignment.end_date) == "2026-12-31"


def test_date_change_validates_against_existing_dates(
    client_for, manager, managed_job, worker, make_assignment
):
    assignment = make_assignment(employee=worker, job=managed_job, start_date=date(2026, 12, 10))

    response = client_for(manager.user).patch(
        url("assignments:detail", pk=assignment.pk), {"end_date": "2026-12-01"}, format="json"
    )

    assert response.status_code == 400


def test_employee_and_job_of_an_assignment_cannot_change(
    client_for, manager, managed_job, worker, make_assignment, other_job
):
    assignment = make_assignment(employee=worker, job=managed_job)

    response = client_for(manager.user).patch(
        url("assignments:detail", pk=assignment.pk), {"job_id": other_job.pk}, format="json"
    )

    assert response.status_code == 400


def test_leadhand_cannot_change_crew_assignment_dates(
    client_for, leadhand, managed_job, worker, make_assignment
):
    assignment = make_assignment(employee=worker, job=managed_job)

    response = client_for(leadhand.user).patch(
        url("assignments:detail", pk=assignment.pk), {"end_date": "2026-12-31"}, format="json"
    )

    assert response.status_code == 403


# --- Ending and cancelling -------------------------------------------------------------------


def test_ending_defaults_to_today_and_keeps_history(
    client_for, manager, managed_job, worker, make_assignment
):
    assignment = make_assignment(employee=worker, job=managed_job)

    response = client_for(manager.user).post(url("assignments:end", pk=assignment.pk))

    assert response.status_code == 200, response.json()
    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.ENDED
    assert assignment.end_date == today()
    assert JobAssignment.objects.filter(pk=assignment.pk).exists()


def test_ending_with_a_past_date(client_for, manager, managed_job, worker, make_assignment):
    assignment = make_assignment(employee=worker, job=managed_job)
    yesterday = today() - timedelta(days=1)

    client_for(manager.user).post(
        url("assignments:end", pk=assignment.pk), {"end_date": yesterday.isoformat()}, format="json"
    )

    assignment.refresh_from_db()
    assert assignment.end_date == yesterday


def test_ending_in_the_future_is_refused(client_for, manager, managed_job, worker, make_assignment):
    assignment = make_assignment(employee=worker, job=managed_job)

    response = client_for(manager.user).post(
        url("assignments:end", pk=assignment.pk),
        {"end_date": (today() + timedelta(days=1)).isoformat()},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "end_date_in_future"


def test_ending_before_the_start_date_is_refused(
    client_for, manager, managed_job, worker, make_assignment
):
    assignment = make_assignment(employee=worker, job=managed_job, start_date=today())

    response = client_for(manager.user).post(
        url("assignments:end", pk=assignment.pk),
        {"end_date": (today() - timedelta(days=3)).isoformat()},
        format="json",
    )

    assert response.status_code == 400


def test_only_active_assignments_can_be_ended_or_cancelled(
    client_for, manager, managed_job, worker, make_assignment
):
    assignment = make_assignment(employee=worker, job=managed_job, status=AssignmentStatus.ENDED)
    client = client_for(manager.user)

    for name in ("assignments:end", "assignments:cancel"):
        response = client.post(url(name, pk=assignment.pk))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "assignment_not_active"


def test_ending_the_designated_leadhands_assignment_clears_the_designation(
    client_for, manager, managed_job, leadhand
):
    assignment = JobAssignment.objects.get(job=managed_job, employee=leadhand)

    client_for(manager.user).post(url("assignments:end", pk=assignment.pk))

    managed_job.refresh_from_db()
    assert managed_job.lead_hand is None
    assert managed_job.updated_by == manager.user


def test_cancel_without_attendance(client_for, manager, managed_job, worker, make_assignment):
    assignment = make_assignment(employee=worker, job=managed_job)

    response = client_for(manager.user).post(url("assignments:cancel", pk=assignment.pk))

    assert response.status_code == 200
    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.CANCELLED


def test_cancel_with_attendance_is_refused(
    client_for, manager, managed_job, worker, make_assignment
):
    assignment = make_assignment(employee=worker, job=managed_job)
    WorkSession.objects.create(assignment=assignment, work_date=today())

    response = client_for(manager.user).post(url("assignments:cancel", pk=assignment.pk))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "assignment_has_sessions"
    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.ACTIVE


def test_cancel_rejects_a_request_body(client_for, manager, managed_job, worker, make_assignment):
    assignment = make_assignment(employee=worker, job=managed_job)

    response = client_for(manager.user).post(
        url("assignments:cancel", pk=assignment.pk), {"reason": "x"}, format="json"
    )

    assert response.status_code == 400


@pytest.mark.parametrize("role", ["leadhand", "worker"])
def test_leadhands_and_employees_cannot_end_or_cancel(
    request, client_for, managed_job, worker, make_assignment, role
):
    assignment = make_assignment(employee=worker, job=managed_job)
    client = client_for(request.getfixturevalue(role).user)

    assert client.post(url("assignments:end", pk=assignment.pk)).status_code == 403
    assert client.post(url("assignments:cancel", pk=assignment.pk)).status_code == 403


def test_reassigning_after_ending_creates_a_new_row(
    client_for, manager, managed_job, worker, make_assignment
):
    first = make_assignment(employee=worker, job=managed_job)
    client = client_for(manager.user)
    client.post(url("assignments:end", pk=first.pk))

    response = assign(client, managed_job, [worker])

    assert results_by_employee(response)[worker.pk]["code"] == "assigned"
    rows = JobAssignment.objects.filter(employee=worker, job=managed_job).order_by("assigned_at")
    assert [r.status for r in rows] == ["ended", "active"]  # history preserved


def test_completing_a_job_does_not_end_its_assignments(
    client_for, manager, managed_job, worker, make_assignment
):
    assignment = make_assignment(employee=worker, job=managed_job)

    client_for(manager.user).patch(
        url("jobs:detail", pk=managed_job.pk), {"status": JobStatus.COMPLETED}, format="json"
    )

    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.ACTIVE
