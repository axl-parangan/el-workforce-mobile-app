"""Timekeeping driven by the jobs API: assignment lifecycle, designation, job edits.

Q6 depends on when an assignment was ended, so those tests use times relative
to now. Everything else uses fixed past times.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.jobs.models import JobAssignment
from apps.timekeeping.models import AttendanceBatch, PunchType, WorkSession
from common.timezones import work_date_for

from .conftest import MORNING, NOON, OUTSIDE, event, url

pytestmark = pytest.mark.django_db


def jobs_url(name, **kwargs):
    return reverse(f"v1:{name}", kwargs=kwargs or None)


def ago(**delta) -> str:
    return (timezone.now() - timedelta(**delta)).isoformat()


@pytest.fixture
def manager_client(client_for, make_employee):
    return client_for(make_employee(role=Role.MANAGER).user)


@pytest.fixture
def worker_assignment(worker, job, assign):
    return assign(worker, job)


def end(manager_client, assignment, **body):
    response = manager_client.post(
        jobs_url("assignments:end", pk=assignment.pk), body or None, format="json"
    )
    assert response.status_code == 200, response.json()


def sync_clock_in(client, job, captured_at):
    response = client.post(
        url("sync"),
        {"events": [event(job, captured_at=captured_at, action_type=PunchType.CLOCK_IN)]},
        format="json",
    )
    return response.json()["results"][0]["batch"]["results"][0]


# --- Q6: offline punches after an assignment ends -------------------------------------


def test_offline_punch_captured_before_the_assignment_ended_is_accepted(
    client_for, worker, job, worker_assignment, manager_client
):
    captured = ago(hours=2)
    end(manager_client, worker_assignment)  # ended now, end date today

    result = sync_clock_in(client_for(worker.user), job, captured)

    assert result["code"] == "clocked_in"
    session = WorkSession.objects.get(pk=result["session_id"])
    assert session.assignment == worker_assignment  # the ended assignment


def test_live_clock_in_after_the_assignment_ended_is_refused(
    client_for, worker, job, worker_assignment, manager_client
):
    end(manager_client, worker_assignment)

    response = client_for(worker.user).post(
        url("clock-in"), event(job, captured_at=timezone.now().isoformat()), format="json"
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "no_active_assignment"


def test_offline_punch_dated_after_the_end_date_is_refused(
    client_for, worker, job, worker_assignment, manager_client
):
    captured = timezone.now() - timedelta(minutes=5)  # before the end was recorded
    # End the day before the punch's own work date (robust around midnight).
    end_date = (work_date_for(captured) - timedelta(days=1)).isoformat()
    end(manager_client, worker_assignment, end_date=end_date)

    result = sync_clock_in(client_for(worker.user), job, captured.isoformat())

    assert result["code"] == "no_active_assignment"


def test_cancelled_assignments_never_authorise_punches(
    client_for, worker, job, worker_assignment, manager_client
):
    captured = ago(hours=1)
    manager_client.post(jobs_url("assignments:cancel", pk=worker_assignment.pk))

    result = sync_clock_in(client_for(worker.user), job, captured)

    assert result["code"] == "no_active_assignment"


def test_replayed_offline_punch_is_unaffected_by_a_later_end(
    client_for, worker, job, worker_assignment, manager_client
):
    payload = event(job, captured_at=ago(hours=1), action_type=PunchType.CLOCK_IN)
    client = client_for(worker.user)
    first = client.post(url("sync"), {"events": [payload]}, format="json").json()
    end(manager_client, worker_assignment)

    retry = client.post(url("sync"), {"events": [payload]}, format="json").json()

    assert retry["results"][0]["batch"]["replayed"] is True
    assert retry["results"][0]["batch"]["results"] == first["results"][0]["batch"]["results"]


# --- Q5: ending while clocked in ------------------------------------------------------------


def test_employee_can_clock_out_after_their_assignment_ended(
    client_for, worker, job, worker_assignment, manager_client
):
    client = client_for(worker.user)
    client.post(url("clock-in"), event(job, captured_at=ago(hours=3)), format="json")
    end(manager_client, worker_assignment)

    response = client.post(
        url("clock-out"), event(job, captured_at=timezone.now().isoformat()), format="json"
    )

    assert response.status_code == 201, response.json()
    assert response.json()["results"][0]["code"] == "clocked_out"
    session = WorkSession.objects.get(assignment=worker_assignment)
    assert session.session_status == "closed"


# --- Designation changes LeadHand access immediately ----------------------------------


def test_new_designation_switches_group_punch_access(
    client_for, leadhand_client, manager_client, make_employee, worker, job, worker_assignment
):
    new_lead = make_employee(role=Role.LEADHAND)
    manager_client.put(
        jobs_url("jobs:lead-hand", pk=job.pk), {"employee_id": new_lead.pk}, format="json"
    )

    old = leadhand_client.post(
        url("group-clock-in"), event(job, employee_ids=[worker.pk]), format="json"
    )
    new = client_for(new_lead.user).post(
        url("group-clock-in"), event(job, employee_ids=[worker.pk]), format="json"
    )

    assert old.status_code == 403
    assert new.status_code == 201
    assert new.json()["results"][0]["code"] == "clocked_in"


def test_ending_the_leadhands_assignment_removes_their_crew_access(
    leadhand_client, manager_client, leadhand, worker, job, worker_assignment
):
    lead_assignment = JobAssignment.objects.get(job=job, employee=leadhand)
    end(manager_client, lead_assignment)

    response = leadhand_client.post(
        url("group-clock-in"), event(job, employee_ids=[worker.pk]), format="json"
    )

    assert response.status_code == 403
    assert leadhand_client.get(url("crew-status", job_id=job.pk)).status_code == 404


# --- Job edits ------------------------------------------------------------------------------


def test_job_put_on_hold_blocks_clock_in_but_not_clock_out(
    client_for, worker, job, worker_assignment, manager_client
):
    client = client_for(worker.user)
    client.post(url("clock-in"), event(job, captured_at=MORNING), format="json")
    manager_client.patch(jobs_url("jobs:detail", pk=job.pk), {"status": "on_hold"}, format="json")

    clock_out = client.post(url("clock-out"), event(job, captured_at=NOON), format="json")
    clock_in = client.post(
        url("clock-in"), event(job, captured_at="2026-03-10T13:00:00-04:00"), format="json"
    )

    assert clock_out.status_code == 201
    assert clock_in.status_code == 409
    assert clock_in.json()["error"]["code"] == "job_not_active"


def test_geofence_edit_does_not_change_stored_assessments(
    client_for, worker, job, worker_assignment, manager_client
):
    response = client_for(worker.user).post(
        url("clock-in"), event(job, location=OUTSIDE), format="json"
    )
    batch_id = response.json()["batch_id"]

    manager_client.patch(
        jobs_url("jobs:detail", pk=job.pk), {"geofence_radius_meters": 500}, format="json"
    )

    batch = AttendanceBatch.objects.get(pk=batch_id)
    assert batch.location_status == "outside_geofence"
    assert WorkSession.objects.get(assignment=worker_assignment).exception_flags == [
        "outside_geofence"
    ]
