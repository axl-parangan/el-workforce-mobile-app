"""Timekeeping behaviour for all four roles (ADR 011).

Administrative entries (Admin/Manager punching others) must be current, so
those tests use timestamps relative to now; everything else uses fixed
past times from conftest.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.timekeeping.models import (
    AttendanceBatch,
    BatchSource,
    ReviewStatus,
    SessionStatus,
    WorkSession,
    WorkSessionReview,
)

from .conftest import MORNING, NOON, OUTSIDE, event, url

pytestmark = pytest.mark.django_db

COMPANY_WIDE = [Role.ADMIN, Role.MANAGER]


def now(offset_minutes: int = 0) -> str:
    return (timezone.now() + timedelta(minutes=offset_minutes)).isoformat()


@pytest.fixture
def make_staff(make_employee):
    """An Admin or Manager with an Employee record (both are employees too)."""

    def _make_staff(role, **fields):
        return make_employee(role=role, **fields)

    return _make_staff


@pytest.fixture
def crew(make_employee, job, assign):
    members = [make_employee(role=Role.WORKER, name=n) for n in ("Ana", "Ben")]
    for member in members:
        assign(member, job)
    return members


def ids(employees):
    return [employee.pk for employee in employees]


def results_by_employee(response):
    return {result["employee"]["id"]: result for result in response.json()["results"]}


def closed_session_for(client, job, *, at_in=MORNING, at_out=NOON) -> WorkSession:
    first = client.post(url("clock-in"), event(job, captured_at=at_in), format="json")
    assert first.status_code == 201, first.json()
    client.post(url("clock-out"), event(job, captured_at=at_out), format="json")
    return WorkSession.objects.get(pk=first.json()["results"][0]["session_id"])


# --- Individual attendance for every role ---------------------------------------


@pytest.mark.parametrize("role", [Role.ADMIN, Role.MANAGER, Role.LEADHAND, Role.WORKER])
def test_every_role_clocks_in_and_out_for_themselves(make_employee, client_for, job, assign, role):
    employee = make_employee(role=role)
    assign(employee, job)
    client = client_for(employee.user)

    session = closed_session_for(client, job)

    assert session.assignment.employee == employee
    assert session.session_status == SessionStatus.CLOSED
    batch = AttendanceBatch.objects.filter(performed_by=employee.user).first()
    assert batch.source == BatchSource.MOBILE_ONLINE  # a self punch is never an admin entry


@pytest.mark.parametrize("role", COMPANY_WIDE)
def test_self_punch_still_needs_an_active_assignment(make_staff, client_for, job, role):
    staff = make_staff(role)

    response = client_for(staff.user).post(url("clock-in"), event(job), format="json")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "no_active_assignment"


@pytest.mark.parametrize("role", COMPANY_WIDE)
def test_own_history_is_personal_even_for_company_wide_roles(
    make_staff, client_for, worker_client, job, assign, role
):
    staff = make_staff(role)
    assign(staff, job)
    worker_client.post(url("clock-in"), event(job), format="json")

    body = client_for(staff.user).get(url("session-list")).json()

    assert body["count"] == 0


# --- Admin and Manager attendance for others (administrative entries) ---------


@pytest.mark.parametrize("role", COMPANY_WIDE)
def test_company_wide_roles_group_clock_in_on_any_job(make_staff, client_for, job, crew, role):
    staff = make_staff(role)  # not the job's LeadHand and not assigned to it

    response = client_for(staff.user).post(
        url("group-clock-in"),
        event(job, captured_at=now(), employee_ids=ids(crew), reason="Phones are dead"),
        format="json",
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["source"] == BatchSource.ADMIN_ENTRY
    assert body["performed_by"]["id"] == staff.user.pk
    assert body["entry_reason"] == "Phones are dead"
    results = results_by_employee(response)
    assert [results[pk]["code"] for pk in ids(crew)] == ["clocked_in", "clocked_in"]
    # Each employee gets their own session; the actor is recorded separately.
    for member in crew:
        session = WorkSession.objects.get(assignment__employee=member)
        assert session.punches.get().batch_item.batch.performed_by == staff.user


@pytest.mark.parametrize("role", COMPANY_WIDE)
def test_company_wide_roles_group_clock_out(make_staff, client_for, job, crew, role):
    client = client_for(make_staff(role).user)
    client.post(
        url("group-clock-in"),
        event(job, captured_at=now(-5), employee_ids=ids(crew)),
        format="json",
    )

    response = client.post(
        url("group-clock-out"), event(job, captured_at=now(), employee_ids=ids(crew)), format="json"
    )

    assert {r["code"] for r in response.json()["results"]} == {"clocked_out"}
    assert WorkSession.objects.filter(session_status=SessionStatus.CLOSED).count() == 2


def test_admin_entry_keeps_location_but_does_not_flag_the_session(
    make_staff, client_for, job, crew
):
    staff = make_staff(Role.MANAGER)

    response = client_for(staff.user).post(
        url("group-clock-in"),
        event(job, captured_at=now(), employee_ids=ids(crew), location=OUTSIDE),
        format="json",
    )

    location = response.json()["location"]
    assert location["status"] == "outside_geofence"  # preserved for reference
    assert location["distance_meters"] == "111.20"
    assert location["requires_review"] is False
    for member in crew:
        session = WorkSession.objects.get(assignment__employee=member)
        assert session.exception_flags == []
        assert session.review_status == ReviewStatus.NOT_REQUIRED


def test_admin_entry_still_validates_each_employees_assignment(
    make_staff, client_for, make_employee, job, crew
):
    stranger = make_employee(role=Role.WORKER)

    response = client_for(make_staff(Role.ADMIN).user).post(
        url("group-clock-in"),
        event(job, captured_at=now(), employee_ids=[*ids(crew), stranger.pk]),
        format="json",
    )

    results = results_by_employee(response)
    assert results[stranger.pk]["code"] == "no_active_assignment"
    assert results[crew[0].pk]["code"] == "clocked_in"


@pytest.mark.parametrize("role", COMPANY_WIDE)
def test_backdated_admin_entries_are_refused(make_staff, client_for, job, crew, role):
    response = client_for(make_staff(role).user).post(
        url("group-clock-in"),
        event(job, captured_at=MORNING, employee_ids=ids(crew)),
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "admin_entry_not_current"
    assert AttendanceBatch.objects.count() == 0


def test_offline_admin_entries_are_marked_and_must_be_current(make_staff, client_for, job, crew):
    client = client_for(make_staff(Role.MANAGER).user)

    response = client.post(
        url("sync"),
        {
            "events": [
                {
                    **event(job, captured_at=now(), employee_ids=ids(crew)),
                    "action_type": "clock_in",
                },
                {
                    **event(job, captured_at=MORNING, employee_ids=ids(crew)),
                    "action_type": "clock_in",
                },
            ]
        },
        format="json",
    )

    current, backdated = response.json()["results"]
    assert current["batch"]["source"] == BatchSource.ADMIN_ENTRY
    assert backdated["status"] == "error"
    assert backdated["error"]["code"] == "admin_entry_not_current"


def test_company_wide_user_punching_only_themselves_is_not_an_admin_entry(
    make_staff, client_for, job, assign
):
    staff = make_staff(Role.MANAGER)
    assign(staff, job)

    response = client_for(staff.user).post(
        url("group-clock-in"),
        event(job, employee_ids=[staff.pk], location=OUTSIDE),
        format="json",
    )

    assert response.json()["source"] == BatchSource.MOBILE_ONLINE
    session = WorkSession.objects.get(assignment__employee=staff)
    assert session.exception_flags == ["outside_geofence"]  # normal location rules apply


def test_leadhand_clocks_out_an_employee_clocked_in_by_someone_else(
    make_staff, client_for, leadhand_client, job, crew
):
    client_for(make_staff(Role.MANAGER).user).post(
        url("group-clock-in"),
        event(job, captured_at=now(-1), employee_ids=ids(crew)),
        format="json",
    )

    response = leadhand_client.post(
        url("group-clock-out"), event(job, captured_at=now(), employee_ids=ids(crew)), format="json"
    )

    assert {r["code"] for r in response.json()["results"]} == {"clocked_out"}
    assert response.json()["source"] == BatchSource.MOBILE_ONLINE  # LeadHand crew punch


# --- LeadHand scope -------------------------------------------------------------------


@pytest.fixture
def other_leadhand_job(make_employee, make_job, assign):
    """A job managed by a different LeadHand, with its own crew member."""
    other = make_employee(role=Role.LEADHAND, name="Other Lead")
    job = make_job(job_number="J-900", lead_hand=other)
    assign(other, job)
    member = make_employee(role=Role.WORKER, name="Their crew")
    assign(member, job)
    return job, member


def test_leadhand_cannot_group_punch_another_leadhands_crew(leadhand_client, other_leadhand_job):
    job, member = other_leadhand_job

    response = leadhand_client.post(
        url("group-clock-in"), event(job, employee_ids=[member.pk]), format="json"
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_job_lead_hand"


def test_assigned_leadhand_who_is_not_the_jobs_leadhand_cannot_group_punch(
    leadhand_client, leadhand, other_leadhand_job, assign
):
    job, member = other_leadhand_job
    assign(leadhand, job)  # on the crew, but not the job's LeadHand

    response = leadhand_client.post(
        url("group-clock-in"), event(job, employee_ids=[member.pk]), format="json"
    )

    assert response.status_code == 403


def test_leadhand_cannot_see_another_leadhands_crew_or_attendance(
    leadhand_client, client_for, other_leadhand_job
):
    job, member = other_leadhand_job
    punched = client_for(member.user).post(url("clock-in"), event(job), format="json")
    session_id = punched.json()["results"][0]["session_id"]
    client_for(member.user).post(
        url("clock-out"), event(job, captured_at="2026-03-10T07:00:00-04:00"), format="json"
    )  # rejected: before clock-in

    assert leadhand_client.get(url("crew-status", job_id=job.pk)).status_code == 404
    assert leadhand_client.get(url("staff:detail", pk=session_id)).status_code == 404
    assert leadhand_client.get(url("staff:list")).json()["count"] == 0
    assert leadhand_client.get(url("staff:exceptions")).json()["count"] == 0
    assert leadhand_client.get(url("staff:rejected-events")).json()["count"] == 0


def test_leadhand_sees_their_own_crew(leadhand_client, client_for, job, crew):
    client_for(crew[0].user).post(url("clock-in"), event(job), format="json")

    assert leadhand_client.get(url("staff:list")).json()["count"] == 1
    crew_names = {
        m["employee"]["name"]
        for m in leadhand_client.get(url("crew-status", job_id=job.pk)).json()["crew"]
    }
    assert {"Ana", "Ben"} <= crew_names


# --- Employee restrictions -------------------------------------------------------------


def test_employee_cannot_record_attendance_for_others(worker_client, job, crew):
    response = worker_client.post(
        url("group-clock-in"), event(job, employee_ids=ids(crew)), format="json"
    )
    sync = worker_client.post(
        url("sync"),
        {"events": [{**event(job, employee_ids=ids(crew)), "action_type": "clock_in"}]},
        format="json",
    )

    assert response.status_code == 403
    assert sync.json()["results"][0]["error"]["code"] == "group_attendance_not_allowed"
    assert AttendanceBatch.objects.count() == 0


def test_employee_has_no_staff_or_crew_access(worker_client, job):
    assert worker_client.get(url("staff:list")).status_code == 403
    assert worker_client.get(url("crew-status", job_id=job.pk)).status_code == 403


# --- Company-wide visibility ---------------------------------------------------------------


@pytest.mark.parametrize("role", COMPANY_WIDE)
def test_company_wide_roles_see_all_attendance(
    make_staff, client_for, other_leadhand_job, worker_client, job, role
):
    other_job, member = other_leadhand_job
    worker_client.post(url("clock-in"), event(job), format="json")
    client_for(member.user).post(url("clock-in"), event(other_job), format="json")
    client = client_for(make_staff(role).user)

    assert client.get(url("staff:list")).json()["count"] == 2
    assert client.get(url("crew-status", job_id=other_job.pk)).status_code == 200


def test_unknown_job_crew_is_404_for_company_wide_roles(make_staff, client_for):
    assert (
        client_for(make_staff(Role.ADMIN).user).get(url("crew-status", job_id=999999)).status_code
        == 404
    )


# --- Timesheet approval -------------------------------------------------------------------


def review(client, session, decision="approved", reason="Checked."):
    return client.post(
        url("staff:review", pk=session.pk), {"decision": decision, "reason": reason}, format="json"
    )


@pytest.mark.parametrize("role", COMPANY_WIDE)
def test_company_wide_roles_review_other_employees_timesheets(
    make_staff, client_for, worker_client, job, role
):
    session = closed_session_for(worker_client, job)
    reviewer = make_staff(role)

    response = review(client_for(reviewer.user), session)

    assert response.status_code == 201
    assert response.json()["review_status"] == "approved"
    assert WorkSessionReview.objects.get().reviewed_by == reviewer.user


@pytest.mark.parametrize("role", COMPANY_WIDE)
def test_nobody_reviews_their_own_timesheet(make_staff, client_for, job, assign, role):
    staff = make_staff(role)
    assign(staff, job)
    client = client_for(staff.user)
    own = closed_session_for(client, job)

    for decision in ("approved", "rejected"):
        response = review(client, own, decision)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "cannot_review_own_timesheet"
    own.refresh_from_db()
    assert own.review_status == ReviewStatus.NOT_REQUIRED
    assert not WorkSessionReview.objects.exists()


def test_a_managers_timesheet_is_reviewed_by_someone_else(make_staff, client_for, job, assign):
    manager = make_staff(Role.MANAGER)
    assign(manager, job)
    own = closed_session_for(client_for(manager.user), job)

    response = review(client_for(make_staff(Role.ADMIN).user), own)

    assert response.status_code == 201


@pytest.mark.parametrize("role", [Role.LEADHAND, Role.WORKER])
def test_leadhands_and_employees_cannot_approve(
    make_employee, client_for, worker_client, job, role
):
    session = closed_session_for(worker_client, job)

    response = review(client_for(make_employee(role=role).user), session)

    assert response.status_code == 403
    assert not WorkSessionReview.objects.exists()
