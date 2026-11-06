import pytest

from apps.accounts.models import Role
from apps.jobs.models import AssignmentStatus, JobStatus
from apps.timekeeping.models import (
    AttendanceBatch,
    AttendanceBatchItem,
    BatchSource,
    SessionStatus,
    TimePunch,
    WorkSession,
)

from .conftest import AFTERNOON, NOON, event, url

pytestmark = pytest.mark.django_db


def test_successful_clock_in(worker_client, worker, job):
    response = worker_client.post(url("clock-in"), event(job), format="json")

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["action_type"] == "clock_in"
    assert body["source"] == BatchSource.MOBILE_ONLINE
    assert body["replayed"] is False
    assert body["captured_at"] == "2026-03-10T08:00:00-04:00"  # company timezone
    [result] = body["results"]
    assert result["employee"] == {"id": worker.pk, "name": "Wendy Worker"}
    assert result["status"] == "accepted"
    assert result["code"] == "clocked_in"

    session = WorkSession.objects.get(pk=result["session_id"])
    assert session.assignment.employee == worker
    assert session.session_status == SessionStatus.OPEN
    assert str(session.work_date) == "2026-03-10"


def test_successful_clock_out_closes_session_with_device_times(worker_client, job):
    clock_in = worker_client.post(url("clock-in"), event(job), format="json").json()
    response = worker_client.post(url("clock-out"), event(job, captured_at=NOON), format="json")

    assert response.status_code == 201, response.json()
    [result] = response.json()["results"]
    assert result["code"] == "clocked_out"
    assert result["session_id"] == clock_in["results"][0]["session_id"]

    session = WorkSession.objects.get(pk=result["session_id"])
    assert session.session_status == SessionStatus.CLOSED
    assert session.punches.count() == 2


def test_duplicate_clock_in_is_rejected_and_recorded(worker_client, job):
    worker_client.post(url("clock-in"), event(job), format="json")

    response = worker_client.post(url("clock-in"), event(job, captured_at=NOON), format="json")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "already_clocked_in"
    assert "J-100" in error["message"]
    assert error["details"]["result"]["results"][0]["status"] == "rejected"
    assert WorkSession.objects.count() == 1
    assert AttendanceBatchItem.objects.filter(result_code="already_clocked_in").count() == 1


def test_clock_out_without_open_session(worker_client, job):
    response = worker_client.post(url("clock-out"), event(job), format="json")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_open_session"
    assert TimePunch.objects.count() == 0


def test_clock_in_without_active_assignment(client_for, make_employee, job):
    unassigned = make_employee(role=Role.WORKER)

    response = client_for(unassigned.user).post(url("clock-in"), event(job), format="json")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "no_active_assignment"
    assert WorkSession.objects.count() == 0


def test_ended_assignment_does_not_authorise_clock_in(client_for, worker, job, assign):
    assign(worker, job, status=AssignmentStatus.ENDED)

    response = client_for(worker.user).post(url("clock-in"), event(job), format="json")

    assert response.json()["error"]["code"] == "no_active_assignment"


def test_assignment_outside_its_dates_does_not_authorise(client_for, worker, job, assign):
    assign(worker, job, start_date="2026-04-01")

    response = client_for(worker.user).post(url("clock-in"), event(job), format="json")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "assignment_not_in_effect"


def test_clock_in_to_another_job_while_clocked_in(worker_client, worker, job, other_job, assign):
    assign(worker, other_job)
    worker_client.post(url("clock-in"), event(job), format="json")

    response = worker_client.post(
        url("clock-in"), event(other_job, captured_at=NOON), format="json"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_clocked_in"


def test_clock_out_of_a_different_job_than_the_open_session(
    worker_client, worker, job, other_job, assign
):
    assign(worker, other_job)
    worker_client.post(url("clock-in"), event(job), format="json")

    response = worker_client.post(
        url("clock-out"), event(other_job, captured_at=NOON), format="json"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "open_session_on_other_job"


def test_can_start_a_new_session_after_clocking_out(worker_client, worker, job, other_job, assign):
    assign(worker, other_job)
    worker_client.post(url("clock-in"), event(job), format="json")
    worker_client.post(url("clock-out"), event(job, captured_at=NOON), format="json")

    response = worker_client.post(
        url("clock-in"), event(other_job, captured_at=AFTERNOON), format="json"
    )

    assert response.status_code == 201
    assert WorkSession.objects.count() == 2


def test_clock_in_on_inactive_job_is_rejected(worker_client, job):
    job.status = JobStatus.COMPLETED
    job.save()

    response = worker_client.post(url("clock-in"), event(job), format="json")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "job_not_active"


def test_inactive_employee_cannot_clock_in(worker_client, worker, job):
    worker.is_active = False
    worker.save()

    response = worker_client.post(url("clock-in"), event(job), format="json")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "employee_inactive"


def test_user_without_employee_record_cannot_punch(client_for, make_user, job):
    response = client_for(make_user(role=Role.ADMIN)).post(
        url("clock-in"), event(job), format="json"
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "no_employee_profile"
    assert AttendanceBatch.objects.count() == 0


def test_employee_identity_comes_from_the_token_not_the_payload(
    worker_client, worker, make_employee, job
):
    someone_else = make_employee(role=None)

    response = worker_client.post(
        url("clock-in"), event(job, employee_ids=[someone_else.pk]), format="json"
    )

    assert response.status_code == 201
    assert response.json()["results"][0]["employee"]["id"] == worker.pk
    assert not WorkSession.objects.filter(assignment__employee=someone_else).exists()


def test_retrying_an_online_clock_in_replays_the_original_result(worker_client, job):
    payload = event(job)
    first = worker_client.post(url("clock-in"), payload, format="json")
    second = worker_client.post(url("clock-in"), payload, format="json")

    assert first.status_code == second.status_code == 201
    assert second.json()["replayed"] is True
    assert {**second.json(), "replayed": False} == first.json()
    assert WorkSession.objects.count() == 1


def test_retrying_a_rejected_punch_replays_the_same_rejection(worker_client, job):
    payload = event(job)
    first = worker_client.post(url("clock-out"), payload, format="json")
    second = worker_client.post(url("clock-out"), payload, format="json")

    assert first.status_code == second.status_code == 409
    first_result = first.json()["error"]["details"]["result"]
    second_result = second.json()["error"]["details"]["result"]
    assert {**second_result, "replayed": False} == first_result
    assert AttendanceBatch.objects.count() == 1


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"event_id": "not-a-uuid"}, "event_id"),
        ({"event_id": None}, "event_id"),
        ({"job_id": 999999}, "job_id"),
        ({"captured_at": "2026-03-10T08:00:00"}, "captured_at"),  # no UTC offset
        ({"captured_at": "yesterday"}, "captured_at"),
    ],
)
def test_structurally_invalid_requests_are_rejected(worker_client, job, change, field):
    payload = {**event(job), **change}

    response = worker_client.post(url("clock-in"), payload, format="json")

    assert response.status_code == 400
    assert field in response.json()["error"]["details"]
    assert AttendanceBatch.objects.count() == 0


def test_missing_event_id_is_rejected(worker_client, job):
    payload = event(job)
    del payload["event_id"]

    response = worker_client.post(url("clock-in"), payload, format="json")

    assert response.status_code == 400
    assert "event_id" in response.json()["error"]["details"]


def test_reusing_an_event_id_for_a_different_event_conflicts(worker_client, job):
    payload = event(job)
    worker_client.post(url("clock-in"), payload, format="json")

    response = worker_client.post(url("clock-out"), payload, format="json")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_key_conflict"


def test_another_users_event_id_conflicts_without_revealing_it(
    worker_client, client_for, make_employee, job, assign
):
    payload = event(job)
    worker_client.post(url("clock-in"), payload, format="json")
    colleague = make_employee(role=Role.WORKER)
    assign(colleague, job)

    response = client_for(colleague.user).post(url("clock-in"), payload, format="json")

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "idempotency_key_conflict",
        "message": "This event_id has already been used.",
    }


def test_unauthenticated_requests_are_refused(api_client, job):
    response = api_client.post(url("clock-in"), event(job), format="json")

    assert response.status_code == 401
