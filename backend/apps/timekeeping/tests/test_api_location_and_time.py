"""GPS assessment and timezone handling, end to end through the API."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.timekeeping.models import AttendanceBatch, ReviewStatus, WorkSession

from .conftest import INSIDE, OUTSIDE, event, url

pytestmark = pytest.mark.django_db


def clock_in(client, job, **kwargs):
    response = client.post(url("clock-in"), event(job, **kwargs), format="json")
    assert response.status_code == 201, response.json()
    return response.json()


def session_of(body) -> WorkSession:
    return WorkSession.objects.get(pk=body["results"][0]["session_id"])


# --- Location ---------------------------------------------------------------------


def test_inside_geofence_is_verified_and_needs_no_review(worker_client, job):
    body = clock_in(worker_client, job, location=INSIDE)

    assert body["location"] == {
        "status": "verified",
        "flags": [],
        "requires_review": False,
        "latitude": "43.643100",
        "longitude": "-79.387100",
        "accuracy_meters": "10.00",
        "distance_meters": "55.60",
    }
    session = session_of(body)
    assert session.review_status == ReviewStatus.NOT_REQUIRED
    assert session.exception_flags == []


def test_outside_geofence_is_accepted_and_flagged(worker_client, job):
    body = clock_in(worker_client, job, location=OUTSIDE)

    assert body["results"][0]["status"] == "accepted"
    assert body["location"]["status"] == "outside_geofence"
    assert body["location"]["distance_meters"] == "111.20"
    session = session_of(body)
    assert session.exception_flags == ["outside_geofence"]
    assert session.review_status == ReviewStatus.PENDING


def test_poor_accuracy_keeps_coordinates_and_flags(worker_client, job):
    body = clock_in(worker_client, job, location={**INSIDE, "accuracy_meters": 75})

    assert body["location"]["status"] == "low_accuracy"
    assert body["location"]["latitude"] == "43.643100"
    assert session_of(body).exception_flags == ["low_accuracy"]


def test_missing_coordinates_are_accepted_as_location_unavailable(worker_client, job):
    body = clock_in(worker_client, job, location=None)

    assert body["location"]["status"] == "location_unavailable"
    assert body["location"]["latitude"] is None
    assert session_of(body).exception_flags == ["location_unavailable"]


@pytest.mark.parametrize(
    "location",
    [
        {"latitude": "91", "longitude": "-79.3871", "accuracy_meters": 5},
        {"latitude": "43.6", "longitude": "-200", "accuracy_meters": 5},
        {"latitude": "north", "longitude": "west"},
        {"latitude": "43.6"},
        "garbage",
    ],
)
def test_invalid_coordinates_are_discarded_and_the_punch_is_accepted(worker_client, job, location):
    body = clock_in(worker_client, job, location=location)

    assert body["results"][0]["status"] == "accepted"
    assert body["location"]["status"] == "invalid_coordinates"
    batch = AttendanceBatch.objects.get(pk=body["batch_id"])
    assert batch.latitude is None
    assert batch.longitude is None
    assert session_of(body).exception_flags == ["invalid_coordinates"]


def test_job_without_coordinates_is_not_flagged_outside(worker_client, worker, make_job, assign):
    unmapped = make_job(lead_hand=None)
    assign(worker, unmapped)

    body = clock_in(worker_client, unmapped, location=OUTSIDE)

    assert body["location"]["status"] == "geofence_not_configured"
    assert body["location"]["requires_review"] is False
    assert body["location"]["distance_meters"] is None
    session = session_of(body)
    assert session.exception_flags == []
    assert session.review_status == ReviewStatus.NOT_REQUIRED


def test_flags_from_both_punches_are_merged_without_duplicates(worker_client, job):
    body = clock_in(worker_client, job, location=OUTSIDE)
    worker_client.post(
        url("clock-out"),
        event(job, captured_at="2026-03-10T12:00:00-04:00", location=OUTSIDE),
        format="json",
    )
    worker_client.post(
        url("clock-in"),
        event(job, captured_at="2026-03-10T13:00:00-04:00", location=None),
        format="json",
    )

    session = session_of(body)
    assert session.exception_flags == ["outside_geofence"]  # not duplicated


def test_device_time_far_in_the_future_is_flagged(worker_client, job):
    ahead = (timezone.now() + timedelta(hours=2)).isoformat()

    body = clock_in(worker_client, job, captured_at=ahead)

    assert session_of(body).exception_flags == ["future_timestamp"]


def test_small_device_clock_drift_is_tolerated(worker_client, job):
    slightly_ahead = (timezone.now() + timedelta(seconds=60)).isoformat()

    body = clock_in(worker_client, job, captured_at=slightly_ahead)

    assert session_of(body).exception_flags == []


# --- Timezone ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("captured_at", "work_date"),
    [
        # 23:30 Toronto (EST) is already the next day in UTC.
        ("2026-11-07T04:30:00Z", "2026-11-06"),
        # 00:15 Toronto belongs to the new day even though UTC is still 05:15.
        ("2026-11-07T00:15:00-05:00", "2026-11-07"),
        # A phone set to Tokyo time: 13:30 JST on the 7th is 23:30 EST on the 6th.
        ("2026-11-07T13:30:00+09:00", "2026-11-06"),
        # Daylight saving time (EDT, UTC-4) is applied automatically.
        ("2026-07-01T03:30:00Z", "2026-06-30"),
        # The night DST ends (01:30 occurs twice in Toronto on 2026-11-01).
        ("2026-11-01T05:30:00Z", "2026-11-01"),
    ],
)
def test_work_date_uses_the_company_timezone(worker_client, job, captured_at, work_date):
    body = clock_in(worker_client, job, captured_at=captured_at)

    assert str(session_of(body).work_date) == work_date


def test_original_device_time_is_preserved_exactly(worker_client, job):
    body = clock_in(worker_client, job, captured_at="2026-11-07T13:30:00+09:00")

    batch = AttendanceBatch.objects.get(pk=body["batch_id"])
    assert batch.captured_at.isoformat() == "2026-11-07T04:30:00+00:00"
    # Responses are rendered in the company timezone.
    assert body["captured_at"] == "2026-11-06T23:30:00-05:00"
