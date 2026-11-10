"""Employees moving between job sites during one workday.

Example day (Toronto, EDT on 2026-03-10):
  07:00 clock in at A, 10:30 clock out of A, 10:30 clock in at B,
  17:00 clock out of B, 17:30 back to A, 19:00 clock out of A.
"""

import threading
import uuid

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.jobs.models import AssignmentStatus, JobAssignment
from apps.timekeeping.models import (
    AttendanceBatch,
    PunchType,
    SessionStatus,
    TimePunch,
    WorkSession,
)
from apps.timekeeping.selectors.attendance import with_punch_times

from .conftest import INSIDE, OUTSIDE, event, url

pytestmark = pytest.mark.django_db


def at(hhmm: str) -> str:
    return f"2026-03-10T{hhmm}:00-04:00"


def utc(hhmm: str) -> str:
    hours, minutes = (int(part) for part in hhmm.split(":"))
    return f"2026-03-10T{hours + 4:02d}:{minutes:02d}:00+00:00"


@pytest.fixture
def job_a(job):
    return job


@pytest.fixture
def job_b(other_job):
    return other_job


@pytest.fixture
def mover(worker, job_a, job_b, assign):
    """A worker actively assigned to both jobs."""
    assign(worker, job_a)
    assign(worker, job_b)
    return worker


@pytest.fixture
def mover_client(client_for, mover):
    return client_for(mover.user)


def punch(client, name, job, hhmm, location=INSIDE, expect=201):
    response = client.post(
        url(name), event(job, captured_at=at(hhmm), location=location), format="json"
    )
    assert response.status_code == expect, response.json()
    return response.json()


def sessions_of(employee):
    return list(
        with_punch_times(WorkSession.objects.filter(assignment__employee=employee))
        .select_related("assignment__job")
        .order_by("clock_in_at")
    )


def open_sessions(employee) -> int:
    return WorkSession.objects.filter(
        assignment__employee=employee, session_status=SessionStatus.OPEN
    ).count()


def describe(session):
    return (
        session.assignment.job.job_number,
        session.clock_in_at.isoformat(),
        session.clock_out_at.isoformat() if session.clock_out_at else None,
        session.session_status,
    )


# --- Online ---------------------------------------------------------------------------


def test_clock_out_of_a_and_immediately_into_b(mover_client, mover, job_a, job_b):
    punch(mover_client, "clock-in", job_a, "07:00")
    punch(mover_client, "clock-out", job_a, "10:30")
    punch(mover_client, "clock-in", job_b, "10:30")  # same instant: touching, not overlapping
    punch(mover_client, "clock-out", job_b, "17:00")

    sessions = sessions_of(mover)
    assert [describe(s) for s in sessions] == [
        ("J-100", utc("07:00"), utc("10:30"), "closed"),
        ("J-200", utc("10:30"), utc("17:00"), "closed"),
    ]
    assert {str(s.work_date) for s in sessions} == {"2026-03-10"}
    assert sessions[0].assignment.job == job_a
    assert sessions[1].assignment.job == job_b
    assert sessions[0].assignment_id != sessions[1].assignment_id


def test_returning_to_a_later_the_same_day(mover_client, mover, job_a, job_b):
    steps = [
        ("clock-in", job_a, "07:00"),
        ("clock-out", job_a, "10:30"),
        ("clock-in", job_b, "10:30"),
        ("clock-out", job_b, "17:00"),
        ("clock-in", job_a, "17:30"),
        ("clock-out", job_a, "19:00"),
    ]
    for name, job, hhmm in steps:
        punch(mover_client, name, job, hhmm)
        assert open_sessions(mover) <= 1

    sessions = sessions_of(mover)
    assert [describe(s) for s in sessions] == [
        ("J-100", utc("07:00"), utc("10:30"), "closed"),
        ("J-200", utc("10:30"), utc("17:00"), "closed"),
        ("J-100", utc("17:30"), utc("19:00"), "closed"),
    ]
    # Both visits to A use the same assignment, as separate sessions.
    assert sessions[0].assignment_id == sessions[2].assignment_id
    assert sessions[0].pk != sessions[2].pk


def test_clocking_into_b_without_leaving_a_is_refused(mover_client, mover, job_a, job_b):
    punch(mover_client, "clock-in", job_a, "07:00")

    body = punch(mover_client, "clock-in", job_b, "10:30", expect=409)

    assert body["error"]["code"] == "already_clocked_in"
    assert "J-100" in body["error"]["message"]
    assert not WorkSession.objects.filter(assignment__job=job_b).exists()
    assert open_sessions(mover) == 1
    assert sessions_of(mover)[0].assignment.job == job_a


def test_moving_never_touches_either_assignment(mover_client, mover, job_a, job_b):
    before = {
        a.pk: (a.status, a.end_date, a.updated_at)
        for a in JobAssignment.objects.filter(employee=mover)
    }

    punch(mover_client, "clock-in", job_a, "07:00")
    punch(mover_client, "clock-out", job_a, "10:30")
    punch(mover_client, "clock-in", job_b, "10:30")

    after = {
        a.pk: (a.status, a.end_date, a.updated_at)
        for a in JobAssignment.objects.filter(employee=mover)
    }
    assert after == before
    assert all(status == AssignmentStatus.ACTIVE for status, _, _ in after.values())


def test_each_session_keeps_its_own_location(mover_client, mover, job_a, job_b):
    punch(mover_client, "clock-in", job_a, "07:00", location=INSIDE)
    punch(mover_client, "clock-out", job_a, "10:30", location=INSIDE)
    punch(mover_client, "clock-in", job_b, "10:30", location=OUTSIDE)
    punch(mover_client, "clock-out", job_b, "17:00", location=INSIDE)

    session_a, session_b = sessions_of(mover)
    assert session_a.exception_flags == []
    assert session_b.exception_flags == ["outside_geofence"]
    batch_b_in = session_b.punches.get(punch_type="clock_in").batch_item.batch
    assert batch_b_in.location_status == "outside_geofence"
    assert str(batch_b_in.distance_meters) == "111.20"


def test_clock_out_naming_the_wrong_job_is_refused(mover_client, mover, job_a, job_b):
    punch(mover_client, "clock-in", job_a, "07:00")

    body = punch(mover_client, "clock-out", job_b, "10:30", expect=409)

    assert body["error"]["code"] == "open_session_on_other_job"
    session = sessions_of(mover)[0]
    assert session.session_status == SessionStatus.OPEN
    assert session.clock_out_at is None


# --- Offline -------------------------------------------------------------------------------


def offline(job, action, hhmm, location=INSIDE):
    return event(job, captured_at=at(hhmm), location=location, action_type=action)


def sync(client, events):
    response = client.post(url("sync"), {"events": events}, format="json")
    assert response.status_code == 200, response.json()
    return response.json()["results"]


def codes(results):
    return [r["batch"]["results"][0]["code"] for r in results]


def test_offline_day_across_jobs_uploaded_out_of_order(mover_client, mover, job_a, job_b):
    day = [
        offline(job_a, PunchType.CLOCK_OUT, "19:00"),
        offline(job_b, PunchType.CLOCK_IN, "10:30"),
        offline(job_a, PunchType.CLOCK_IN, "07:00"),
        offline(job_a, PunchType.CLOCK_IN, "17:30"),
        offline(job_b, PunchType.CLOCK_OUT, "17:00"),
        offline(job_a, PunchType.CLOCK_OUT, "10:30"),
    ]

    results = sync(mover_client, day)

    assert all(r["status"] == "processed" for r in results)
    assert set(codes(results)) == {"clocked_in", "clocked_out"}
    assert [describe(s) for s in sessions_of(mover)] == [
        ("J-100", utc("07:00"), utc("10:30"), "closed"),
        ("J-200", utc("10:30"), utc("17:00"), "closed"),
        ("J-100", utc("17:30"), utc("19:00"), "closed"),
    ]


def test_equal_timestamps_close_before_opening(mover_client, mover, job_a, job_b):
    """Q13: the queue lists B's clock-in before A's clock-out at the same instant."""
    results = sync(
        mover_client,
        [
            offline(job_a, PunchType.CLOCK_IN, "07:00"),
            offline(job_b, PunchType.CLOCK_IN, "10:30"),
            offline(job_a, PunchType.CLOCK_OUT, "10:30"),
        ],
    )

    assert codes(results) == ["clocked_in", "clocked_in", "clocked_out"]
    assert [describe(s) for s in sessions_of(mover)] == [
        ("J-100", utc("07:00"), utc("10:30"), "closed"),
        ("J-200", utc("10:30"), None, "open"),
    ]


def test_retrying_the_whole_day_creates_nothing_new(mover_client, mover, job_a, job_b):
    day = [
        offline(job_a, PunchType.CLOCK_IN, "07:00"),
        offline(job_a, PunchType.CLOCK_OUT, "10:30"),
        offline(job_b, PunchType.CLOCK_IN, "10:30"),
        offline(job_b, PunchType.CLOCK_OUT, "17:00"),
    ]
    first = sync(mover_client, day)
    counts = (
        WorkSession.objects.count(),
        TimePunch.objects.count(),
        AttendanceBatch.objects.count(),
    )

    retry = sync(mover_client, day)
    retry_shuffled = sync(mover_client, list(reversed(day)))

    assert all(r["batch"]["replayed"] for r in retry + retry_shuffled)
    assert [{**r["batch"], "replayed": False} for r in retry] == [r["batch"] for r in first]
    assert (
        (
            WorkSession.objects.count(),
            TimePunch.objects.count(),
            AttendanceBatch.objects.count(),
        )
        == counts
        == (2, 4, 4)
    )


def test_online_move_then_offline_retry_of_the_same_events(mover_client, mover, job_a, job_b):
    clock_out_a = event(job_a, captured_at=at("10:30"))
    clock_in_b = event(job_b, captured_at=at("10:30"))
    punch(mover_client, "clock-in", job_a, "07:00")
    mover_client.post(url("clock-out"), clock_out_a, format="json")
    mover_client.post(url("clock-in"), clock_in_b, format="json")

    results = sync(
        mover_client,
        [{**clock_in_b, "action_type": "clock_in"}, {**clock_out_a, "action_type": "clock_out"}],
    )

    assert [r["batch"]["replayed"] for r in results] == [True, True]
    assert WorkSession.objects.count() == 2


# --- LeadHand-driven moves (Q14) -------------------------------------------------------


@pytest.fixture
def lead_b(make_employee, assign):
    return make_employee(role=Role.LEADHAND, name="Bea Lead")


@pytest.fixture
def job_led_by_b(make_job, assign, lead_b, mover):
    job = make_job(job_number="J-300", lead_hand=lead_b)
    assign(lead_b, job)
    assign(mover, job)
    return job


def group(client, name, job, hhmm, employees):
    return client.post(
        url(name),
        event(job, captured_at=at(hhmm), employee_ids=[e.pk for e in employees]),
        format="json",
    )


def test_leadhands_move_a_worker_between_their_jobs(
    leadhand_client, client_for, lead_b, mover, job_a, job_led_by_b
):
    lead_b_client = client_for(lead_b.user)
    group(leadhand_client, "group-clock-in", job_a, "07:00", [mover])

    # B's LeadHand cannot close the session on A (no cross-job takeover).
    takeover = group(lead_b_client, "group-clock-out", job_a, "10:30", [mover])
    assert takeover.status_code == 403
    assert takeover.json()["error"]["code"] == "not_job_lead_hand"
    # Nor clock the worker in at B while they are still open at A.
    early = group(lead_b_client, "group-clock-in", job_led_by_b, "10:30", [mover])
    assert early.json()["results"][0]["code"] == "already_clocked_in"

    out_a = group(leadhand_client, "group-clock-out", job_a, "10:30", [mover])
    in_b = group(lead_b_client, "group-clock-in", job_led_by_b, "10:31", [mover])

    assert out_a.json()["results"][0]["code"] == "clocked_out"
    assert in_b.json()["results"][0]["code"] == "clocked_in"
    assert [s.assignment.job.job_number for s in sessions_of(mover)] == ["J-100", "J-300"]


# --- Concurrency (real transactions) --------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_simultaneous_clock_ins_at_two_jobs_leave_one_open_session(mover, job_a, job_b):
    client = APIClient()
    client.force_authenticate(mover.user)
    barrier = threading.Barrier(2)
    statuses = []

    def run(job):
        try:
            barrier.wait()
            payload = {**event(job, captured_at=at("07:00")), "event_id": str(uuid.uuid4())}
            statuses.append(client.post(url("clock-in"), payload, format="json").status_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(job,)) for job in (job_a, job_b)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(statuses) == [201, 409]
    assert open_sessions(mover) == 1
