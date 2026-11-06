import pytest

from apps.accounts.models import Role
from apps.timekeeping.models import AttendanceBatch, SessionStatus, WorkSession

from .conftest import MORNING, NOON, event, url

pytestmark = pytest.mark.django_db


@pytest.fixture
def crew(make_employee, job, assign):
    """Three employees assigned to the job; the last has no app account."""
    members = [
        make_employee(role=Role.WORKER, name="Ana"),
        make_employee(role=Role.WORKER, name="Ben"),
        make_employee(role=None, name="Cal (no account)"),
    ]
    for member in members:
        assign(member, job)
    return members


def ids(employees):
    return [employee.pk for employee in employees]


def results_by_employee(response):
    return {result["employee"]["id"]: result for result in response.json()["results"]}


def test_leadhand_clocks_in_multiple_workers_individually(leadhand_client, leadhand, job, crew):
    response = leadhand_client.post(
        url("group-clock-in"), event(job, employee_ids=ids(crew)), format="json"
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["performed_by"]["id"] == leadhand.user.pk
    results = results_by_employee(response)
    assert set(results) == set(ids(crew))
    assert {result["code"] for result in results.values()} == {"clocked_in"}

    # One individual session per employee, never a shared one.
    session_ids = {result["session_id"] for result in results.values()}
    assert len(session_ids) == 3
    for member in crew:
        session = WorkSession.objects.get(assignment__employee=member)
        assert session.session_status == SessionStatus.OPEN
    assert AttendanceBatch.objects.get().items.count() == 3


def test_leadhand_clocks_out_multiple_workers(leadhand_client, job, crew):
    leadhand_client.post(url("group-clock-in"), event(job, employee_ids=ids(crew)), format="json")

    response = leadhand_client.post(
        url("group-clock-out"), event(job, captured_at=NOON, employee_ids=ids(crew)), format="json"
    )

    assert response.status_code == 201
    assert {r["code"] for r in response.json()["results"]} == {"clocked_out"}
    assert WorkSession.objects.filter(session_status=SessionStatus.CLOSED).count() == 3


def test_unassigned_worker_fails_while_others_succeed(leadhand_client, job, crew, make_employee):
    stranger = make_employee(role=Role.WORKER, name="Stranger")

    response = leadhand_client.post(
        url("group-clock-in"), event(job, employee_ids=[*ids(crew), stranger.pk]), format="json"
    )

    assert response.status_code == 201
    results = results_by_employee(response)
    assert results[stranger.pk]["status"] == "rejected"
    assert results[stranger.pk]["code"] == "no_active_assignment"
    assert [results[pk]["code"] for pk in ids(crew)] == ["clocked_in"] * 3
    assert WorkSession.objects.count() == 3


def test_already_clocked_in_worker_fails_individually(leadhand_client, client_for, job, crew):
    client_for(crew[0].user).post(url("clock-in"), event(job), format="json")

    response = leadhand_client.post(
        url("group-clock-in"), event(job, captured_at=NOON, employee_ids=ids(crew)), format="json"
    )

    results = results_by_employee(response)
    assert results[crew[0].pk]["code"] == "already_clocked_in"
    assert results[crew[1].pk]["code"] == "clocked_in"
    assert results[crew[2].pk]["code"] == "clocked_in"


def test_leadhand_of_another_job_is_not_authorised(client_for, make_employee, job, crew):
    other_leadhand = make_employee(role=Role.LEADHAND)

    response = client_for(other_leadhand.user).post(
        url("group-clock-in"), event(job, employee_ids=ids(crew)), format="json"
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_job_lead_hand"
    assert AttendanceBatch.objects.count() == 0


def test_job_without_a_leadhand_cannot_be_group_punched(leadhand_client, make_job, crew):
    unled = make_job(lead_hand=None)

    response = leadhand_client.post(
        url("group-clock-in"), event(unled, employee_ids=ids(crew)), format="json"
    )

    assert response.status_code == 403


def test_workers_cannot_use_group_endpoints(client_for, job, crew):
    response = client_for(crew[0].user).post(
        url("group-clock-in"), event(job, employee_ids=ids(crew)), format="json"
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_leadhand_clocks_themselves_in_with_a_valid_assignment(
    leadhand_client, leadhand, job, crew, assign
):
    assign(leadhand, job)

    response = leadhand_client.post(
        url("group-clock-in"), event(job, employee_ids=[leadhand.pk, *ids(crew)]), format="json"
    )

    results = results_by_employee(response)
    assert results[leadhand.pk]["code"] == "clocked_in"
    assert WorkSession.objects.filter(assignment__employee=leadhand).exists()


def test_leadhand_without_own_assignment_is_not_auto_assigned(leadhand_client, leadhand, job, crew):
    response = leadhand_client.post(
        url("group-clock-in"), event(job, employee_ids=[leadhand.pk]), format="json"
    )

    assert results_by_employee(response)[leadhand.pk]["code"] == "no_active_assignment"
    assert not leadhand.job_assignments.exists()


def test_leadhand_self_punch_via_individual_endpoint(leadhand_client, leadhand, job, assign):
    assign(leadhand, job)

    response = leadhand_client.post(url("clock-in"), event(job), format="json")

    assert response.status_code == 201
    assert response.json()["results"][0]["employee"]["id"] == leadhand.pk


def test_duplicate_group_submission_is_replayed(leadhand_client, job, crew):
    payload = event(job, employee_ids=ids(crew))

    first = leadhand_client.post(url("group-clock-in"), payload, format="json")
    second = leadhand_client.post(url("group-clock-in"), payload, format="json")

    assert second.status_code == 201
    assert second.json()["replayed"] is True
    assert {**second.json(), "replayed": False} == first.json()
    assert WorkSession.objects.count() == 3
    assert AttendanceBatch.objects.count() == 1


def test_resubmitting_an_event_id_with_different_employees_conflicts(leadhand_client, job, crew):
    payload = event(job, employee_ids=ids(crew))
    leadhand_client.post(url("group-clock-in"), payload, format="json")

    response = leadhand_client.post(
        url("group-clock-in"), {**payload, "employee_ids": ids(crew[:2])}, format="json"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_key_conflict"


@pytest.mark.parametrize(
    "employee_ids",
    [[], "not-a-list", [0]],
)
def test_invalid_employee_lists_are_rejected(leadhand_client, job, employee_ids):
    response = leadhand_client.post(
        url("group-clock-in"), event(job, employee_ids=employee_ids), format="json"
    )

    assert response.status_code == 400
    assert "employee_ids" in response.json()["error"]["details"]


def test_duplicate_and_unknown_employee_ids_are_rejected(leadhand_client, job, crew):
    duplicate = leadhand_client.post(
        url("group-clock-in"), event(job, employee_ids=[crew[0].pk, crew[0].pk]), format="json"
    )
    unknown = leadhand_client.post(
        url("group-clock-in"), event(job, employee_ids=[crew[0].pk, 999999]), format="json"
    )

    assert duplicate.status_code == unknown.status_code == 400
    assert "999999" in str(unknown.json()["error"]["details"]["employee_ids"])
    assert AttendanceBatch.objects.count() == 0


def test_group_location_comes_from_the_leadhand_device(leadhand_client, job, crew):
    response = leadhand_client.post(
        url("group-clock-in"),
        event(job, captured_at=MORNING, employee_ids=ids(crew), location=None),
        format="json",
    )

    assert response.json()["location"]["status"] == "location_unavailable"
    for member in crew:
        session = WorkSession.objects.get(assignment__employee=member)
        assert session.exception_flags == ["location_unavailable"]
