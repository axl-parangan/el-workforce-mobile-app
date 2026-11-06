"""Current status, attendance history, and crew status."""

import pytest

from apps.accounts.models import Role

from .conftest import AFTERNOON, EVENING, MORNING, NOON, event, url

pytestmark = pytest.mark.django_db


def punch(client, name, job, at):
    response = client.post(url(name), event(job, captured_at=at), format="json")
    assert response.status_code == 201, response.json()
    return response.json()


def test_status_when_not_clocked_in(worker_client, worker):
    response = worker_client.get(url("status"))

    assert response.status_code == 200
    assert response.json() == {
        "employee": {"id": worker.pk, "name": "Wendy Worker"},
        "clocked_in": False,
        "open_session": None,
    }


def test_status_when_clocked_in(worker_client, job):
    punch(worker_client, "clock-in", job, MORNING)

    body = worker_client.get(url("status")).json()

    assert body["clocked_in"] is True
    session = body["open_session"]
    assert session["job"]["job_number"] == "J-100"
    assert session["clock_in"]["at"] == "2026-03-10T08:00:00-04:00"
    assert session["clock_out"] is None
    assert session["duration_seconds"] is None


def test_status_requires_an_employee_record(client_for, make_user):
    response = client_for(make_user(role=Role.ADMIN)).get(url("status"))

    assert response.status_code == 403


def test_session_history_is_newest_first_with_durations(worker_client, job):
    punch(worker_client, "clock-in", job, MORNING)
    punch(worker_client, "clock-out", job, NOON)
    punch(worker_client, "clock-in", job, AFTERNOON)
    punch(worker_client, "clock-out", job, EVENING)

    body = worker_client.get(url("session-list")).json()

    assert body["count"] == 2
    first, second = body["results"]
    assert first["clock_in"]["at"] == "2026-03-10T13:00:00-04:00"
    assert first["duration_seconds"] == 4 * 3600
    assert second["clock_in"]["at"] == "2026-03-10T08:00:00-04:00"
    assert second["clock_out"]["location"]["status"] == "verified"


def test_history_filters(worker_client, worker, job, other_job, assign):
    assign(worker, other_job)
    punch(worker_client, "clock-in", job, MORNING)
    punch(worker_client, "clock-out", job, NOON)
    punch(worker_client, "clock-in", other_job, "2026-03-12T08:00:00-04:00")

    by_job = worker_client.get(url("session-list"), {"job_id": other_job.pk}).json()
    by_date = worker_client.get(
        url("session-list"), {"work_date_from": "2026-03-10", "work_date_to": "2026-03-10"}
    ).json()
    bad = worker_client.get(
        url("session-list"), {"work_date_from": "2026-03-12", "work_date_to": "2026-03-10"}
    )

    assert by_job["count"] == 1
    assert by_date["count"] == 1
    assert bad.status_code == 400


def test_worker_cannot_see_another_workers_attendance(
    worker_client, client_for, make_employee, job, assign
):
    colleague = make_employee(role=Role.WORKER)
    assign(colleague, job)
    theirs = punch(client_for(colleague.user), "clock-in", job, MORNING)
    session_id = theirs["results"][0]["session_id"]

    detail = worker_client.get(url("session-detail", pk=session_id))
    listing = worker_client.get(url("session-list")).json()

    assert detail.status_code == 404
    assert listing["count"] == 0


def test_worker_can_read_own_session_detail(worker_client, job):
    mine = punch(worker_client, "clock-in", job, MORNING)

    response = worker_client.get(url("session-detail", pk=mine["results"][0]["session_id"]))

    assert response.status_code == 200
    assert response.json()["clock_in"]["event_id"] == mine["event_id"]


def test_leadhand_crew_status(leadhand_client, client_for, make_employee, job, other_job, assign):
    here, elsewhere, idle = (make_employee(role=Role.WORKER, name=n) for n in ("A", "B", "C"))
    for member in (here, elsewhere, idle):
        assign(member, job)
    assign(elsewhere, other_job)
    punch(client_for(here.user), "clock-in", job, MORNING)
    punch(client_for(elsewhere.user), "clock-in", other_job, MORNING)

    body = leadhand_client.get(url("crew-status", job_id=job.pk)).json()

    crew = {member["employee"]["name"]: member for member in body["crew"]}
    assert crew["A"]["clocked_in"] is True
    assert crew["A"]["open_session"]["job"]["id"] == job.pk
    assert crew["B"]["open_session"]["job"]["id"] == other_job.pk
    assert crew["C"]["clocked_in"] is False


def test_crew_status_is_limited_to_the_jobs_leadhand(client_for, make_employee, job):
    other_leadhand = make_employee(role=Role.LEADHAND)

    assert client_for(other_leadhand.user).get(url("crew-status", job_id=job.pk)).status_code == 404


def test_workers_cannot_view_crew_status(worker_client, job):
    assert worker_client.get(url("crew-status", job_id=job.pk)).status_code == 403
