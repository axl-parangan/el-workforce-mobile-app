import threading
from unittest import mock

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.timekeeping.models import (
    AttendanceBatch,
    BatchSource,
    PunchType,
    ReviewStatus,
    SessionStatus,
    TimePunch,
    WorkSession,
)
from apps.timekeeping.selectors.attendance import with_punch_times

from .conftest import AFTERNOON, EVENING, MORNING, NOON, event, url

pytestmark = pytest.mark.django_db


def sync(client, *events):
    return client.post(url("sync"), {"events": list(events)}, format="json")


def clock_in(job, at=MORNING, **extra):
    return event(job, captured_at=at, action_type=PunchType.CLOCK_IN, **extra)


def clock_out(job, at=NOON, **extra):
    return event(job, captured_at=at, action_type=PunchType.CLOCK_OUT, **extra)


def session_times(session_id):
    session = with_punch_times(WorkSession.objects.filter(pk=session_id)).get()
    return (
        session.clock_in_at.isoformat(),
        session.clock_out_at and session.clock_out_at.isoformat(),
    )


def test_successful_batch_submission(worker_client, worker, job):
    response = sync(worker_client, clock_in(job))

    assert response.status_code == 200
    [result] = response.json()["results"]
    assert result["status"] == "processed"
    batch = result["batch"]
    assert batch["source"] == BatchSource.MOBILE_OFFLINE_SYNC
    assert batch["results"][0]["code"] == "clocked_in"
    assert batch["results"][0]["employee"]["id"] == worker.pk


def test_offline_clock_in_and_clock_out_reconstruct_the_real_work_period(worker_client, job):
    response = sync(worker_client, clock_in(job, MORNING), clock_out(job, NOON))

    results = response.json()["results"]
    assert [r["batch"]["results"][0]["code"] for r in results] == ["clocked_in", "clocked_out"]
    session_id = results[0]["batch"]["results"][0]["session_id"]
    assert session_times(session_id) == (
        "2026-03-10T12:00:00+00:00",  # 08:00 EDT
        "2026-03-10T16:00:00+00:00",  # 12:00 EDT
    )
    session = WorkSession.objects.get(pk=session_id)
    assert session.session_status == SessionStatus.CLOSED
    # The server receipt time is kept separately and never replaces device time.
    batch = AttendanceBatch.objects.get(idempotency_key=results[1]["event_id"])
    assert batch.received_at > batch.captured_at


def test_offline_workday_syncs_exactly_once_into_one_closed_session(worker_client, worker, job):
    """The acceptance scenario: clock in offline at 08:00, clock out offline at 17:00,
    reconnect at 18:00 and upload, then upload again (lost response). Exactly one
    correctly closed 08:00-17:00 session must result."""
    queue = [
        clock_in(job, "2026-11-05T08:00:00-05:00"),
        clock_out(job, "2026-11-05T17:00:00-05:00"),
    ]

    first = sync(worker_client, *queue).json()["results"]
    retry = sync(worker_client, *queue).json()["results"]

    assert [r["batch"]["results"][0]["code"] for r in first] == ["clocked_in", "clocked_out"]
    assert [r["batch"]["replayed"] for r in retry] == [True, True]
    assert [{**r["batch"], "replayed": False} for r in retry] == [r["batch"] for r in first]

    assert AttendanceBatch.objects.count() == 2
    assert TimePunch.objects.count() == 2
    session = WorkSession.objects.get(assignment__employee=worker)
    assert session.session_status == SessionStatus.CLOSED
    assert str(session.work_date) == "2026-11-05"
    assert session_times(session.pk) == (
        "2026-11-05T13:00:00+00:00",  # 08:00 EST
        "2026-11-05T22:00:00+00:00",  # 17:00 EST
    )
    assert worker_client.get(url("status")).json()["clocked_in"] is False
    history = worker_client.get(url("session-list")).json()
    assert history["count"] == 1
    assert history["results"][0]["duration_seconds"] == 9 * 3600


def test_events_are_processed_in_device_time_order_not_submission_order(worker_client, job):
    out_ = clock_out(job, NOON)
    in_ = clock_in(job, MORNING)

    response = sync(worker_client, out_, in_)

    results = response.json()["results"]
    # Results come back in submission order...
    assert [r["event_id"] for r in results] == [out_["event_id"], in_["event_id"]]
    # ...but the clock-in was applied first, so both are accepted.
    assert results[0]["batch"]["results"][0]["code"] == "clocked_out"
    assert results[1]["batch"]["results"][0]["code"] == "clocked_in"


def test_two_offline_sessions_in_one_upload(worker_client, job):
    response = sync(
        worker_client,
        clock_out(job, EVENING),
        clock_in(job, AFTERNOON),
        clock_out(job, NOON),
        clock_in(job, MORNING),
    )

    codes = [r["batch"]["results"][0]["code"] for r in response.json()["results"]]
    assert codes == ["clocked_out", "clocked_in", "clocked_out", "clocked_in"]
    assert WorkSession.objects.filter(session_status=SessionStatus.CLOSED).count() == 2


def test_duplicate_batch_submission_is_idempotent(worker_client, job):
    events = [clock_in(job, MORNING), clock_out(job, NOON)]
    first = sync(worker_client, *events)
    second = sync(worker_client, *events)

    assert AttendanceBatch.objects.count() == 2
    assert WorkSession.objects.count() == 1
    for original, retry in zip(first.json()["results"], second.json()["results"], strict=True):
        assert retry["batch"]["replayed"] is True
        assert {**retry["batch"], "replayed": False} == original["batch"]


def test_duplicate_event_inside_one_submission(worker_client, job):
    in_ = clock_in(job)

    response = sync(worker_client, in_, in_)

    first, second = response.json()["results"]
    assert first["batch"]["replayed"] is False
    assert second["batch"]["replayed"] is True
    assert first["batch"]["batch_id"] == second["batch"]["batch_id"]
    assert WorkSession.objects.count() == 1


def test_event_first_sent_online_then_in_a_sync_is_replayed(worker_client, job):
    payload = event(job)
    online = worker_client.post(url("clock-in"), payload, format="json")

    response = sync(worker_client, {**payload, "action_type": "clock_in"})

    batch = response.json()["results"][0]["batch"]
    assert batch["replayed"] is True
    assert batch["batch_id"] == online.json()["batch_id"]
    assert batch["source"] == BatchSource.MOBILE_ONLINE  # the original source is preserved


def test_batch_with_multiple_employees_from_a_leadhand_device(
    leadhand_client, make_employee, job, assign
):
    crew = [make_employee(role=None), make_employee(role=None)]
    for member in crew:
        assign(member, job)
    ids = [member.pk for member in crew]

    response = sync(
        leadhand_client,
        clock_in(job, MORNING, employee_ids=ids),
        clock_out(job, NOON, employee_ids=ids),
    )

    for result in response.json()["results"]:
        assert {r["status"] for r in result["batch"]["results"]} == {"accepted"}
    assert WorkSession.objects.filter(session_status=SessionStatus.CLOSED).count() == 2


def test_partial_success_and_invalid_events_do_not_block_valid_ones(worker_client, job):
    response = sync(
        worker_client,
        clock_in(job, MORNING),
        {"event_id": "nope", "action_type": "teleport", "job_id": job.pk},
        # Device time 07:00 is processed before the 08:00 clock-in: nothing to close yet.
        clock_out(job, "2026-03-10T07:00:00-04:00"),
        "not even an object",
    )

    results = response.json()["results"]
    assert response.status_code == 200
    assert [r["status"] for r in results] == ["processed", "invalid", "processed", "invalid"]
    assert results[0]["batch"]["results"][0]["code"] == "clocked_in"
    assert set(results[1]["error"]["details"]) >= {"event_id", "action_type", "captured_at"}
    assert results[1]["event_id"] == "nope"
    assert results[2]["batch"]["results"][0]["code"] == "no_open_session"
    assert WorkSession.objects.get().session_status == SessionStatus.OPEN
    assert results[3]["event_id"] is None


def test_unreconcilable_clock_out_flags_the_session_for_review(worker_client, job):
    sync(worker_client, clock_in(job, NOON))

    response = sync(worker_client, clock_out(job, MORNING))

    result = response.json()["results"][0]["batch"]["results"][0]
    assert result["status"] == "rejected"
    session = WorkSession.objects.get()
    assert session.session_status == SessionStatus.OPEN  # not silently closed wrongly
    assert session.exception_flags == ["clock_out_rejected"]
    assert session.review_status == ReviewStatus.PENDING


def test_late_offline_session_overlapping_an_existing_one_is_flagged(
    worker_client, leadhand_client, worker, job
):
    # The LeadHand recorded 10:00-11:00 online; the worker's phone later uploads 08:00-12:00.
    leadhand_client.post(
        url("group-clock-in"),
        event(job, captured_at="2026-03-10T10:00:00-04:00", employee_ids=[worker.pk]),
        format="json",
    )
    leadhand_client.post(
        url("group-clock-out"),
        event(job, captured_at="2026-03-10T11:00:00-04:00", employee_ids=[worker.pk]),
        format="json",
    )

    response = sync(worker_client, clock_in(job, MORNING), clock_out(job, NOON))

    codes = [r["batch"]["results"][0]["code"] for r in response.json()["results"]]
    assert codes == ["clocked_in", "overlaps_existing_session"]
    late = WorkSession.objects.get(session_status=SessionStatus.OPEN)
    assert late.exception_flags == ["clock_out_rejected"]


def test_clock_in_inside_an_existing_session_is_rejected(worker_client, job):
    sync(worker_client, clock_in(job, MORNING), clock_out(job, NOON))

    response = sync(worker_client, clock_in(job, "2026-03-10T10:00:00-04:00"))

    assert response.json()["results"][0]["batch"]["results"][0]["code"] == (
        "overlaps_existing_session"
    )


def test_unauthorised_group_event_is_an_error_result(client_for, make_employee, job, worker):
    other_leadhand = make_employee(role=Role.LEADHAND)

    response = sync(client_for(other_leadhand.user), clock_in(job, employee_ids=[worker.pk]))

    result = response.json()["results"][0]
    assert result["status"] == "error"
    assert result["error"]["code"] == "not_job_lead_hand"
    assert AttendanceBatch.objects.count() == 0


@pytest.mark.parametrize("body", [{}, {"events": []}, {"events": "nope"}])
def test_malformed_envelope_is_a_400(worker_client, body):
    response = worker_client.post(url("sync"), body, format="json")

    assert response.status_code == 400


def test_too_many_events_are_refused(worker_client, job, settings):
    events = [clock_in(job) for _ in range(settings.ATTENDANCE_MAX_SYNC_EVENTS + 1)]

    assert sync(worker_client, *events).status_code == 400


def test_retry_after_a_failed_request_processes_the_event(worker_client, job):
    payload = clock_in(job)
    with mock.patch(
        "apps.timekeeping.services.attendance.process_item",
        side_effect=RuntimeError("connection dropped"),
    ):
        failed = sync(worker_client, payload)

    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "server_error"

    # Nothing was half-written...
    assert AttendanceBatch.objects.count() == 0
    # ...so the retry processes the event normally.
    response = sync(worker_client, payload)
    assert response.json()["results"][0]["batch"]["replayed"] is False
    assert WorkSession.objects.count() == 1


def test_retry_after_a_lost_response_returns_the_stored_result(worker_client, job):
    payload = clock_in(job)
    first = sync(worker_client, payload)  # response "lost" on the way back

    retry = sync(worker_client, payload)

    assert retry.json()["results"][0]["batch"]["replayed"] is True
    assert (
        retry.json()["results"][0]["batch"]["batch_id"]
        == (first.json()["results"][0]["batch"]["batch_id"])
    )


# --- Concurrency (real transactions, separate connections) ---------------------------


def _post_concurrently(requests):
    """Run (client, url, payload) posts in threads that start at the same moment."""
    barrier = threading.Barrier(len(requests))
    responses = [None] * len(requests)

    def run(index, client, path, payload):
        try:
            barrier.wait()
            responses[index] = client.post(path, payload, format="json")
        finally:
            connection.close()

    threads = [
        threading.Thread(target=run, args=(index, *request))
        for index, request in enumerate(requests)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return responses


@pytest.fixture
def authenticated(worker):
    client = APIClient()
    client.force_authenticate(worker.user)
    return client


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_submissions_create_one_record(authenticated, worker, job, assign):
    assign(worker, job)
    payload = {"events": [clock_in(job)]}

    responses = _post_concurrently([(authenticated, url("sync"), payload)] * 4)

    assert [r.status_code for r in responses] == [200] * 4
    batches = [r.json()["results"][0]["batch"] for r in responses]
    assert len({b["batch_id"] for b in batches}) == 1
    assert sorted(b["replayed"] for b in batches) == [False, True, True, True]
    assert AttendanceBatch.objects.count() == 1
    assert WorkSession.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_different_clock_ins_for_one_employee(authenticated, worker, job, assign):
    assign(worker, job)

    responses = _post_concurrently([(authenticated, url("clock-in"), event(job)) for _ in range(3)])

    assert sorted(r.status_code for r in responses) == [201, 409, 409]
    assert WorkSession.objects.count() == 1
