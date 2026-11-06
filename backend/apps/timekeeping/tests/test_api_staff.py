"""Staff attendance views and the review workflow."""

import pytest

from apps.accounts.models import Role
from apps.timekeeping.models import (
    AttendanceBatch,
    ReviewStatus,
    TimePunch,
    WorkSession,
    WorkSessionReview,
)

from .conftest import NOON, OUTSIDE, event, url

pytestmark = pytest.mark.django_db


@pytest.fixture
def flagged_session(worker_client, job):
    """A closed session whose clock-in was outside the geofence."""
    response = worker_client.post(url("clock-in"), event(job, location=OUTSIDE), format="json")
    worker_client.post(url("clock-out"), event(job, captured_at=NOON), format="json")
    return WorkSession.objects.get(pk=response.json()["results"][0]["session_id"])


def review(client, session, decision="approved", reason="Checked with the site supervisor."):
    return client.post(
        url("staff:review", pk=session.pk), {"decision": decision, "reason": reason}, format="json"
    )


# --- Listing -----------------------------------------------------------------------


def test_admin_sees_all_attendance(admin_client, flagged_session):
    body = admin_client.get(url("staff:list")).json()

    assert body["count"] == 1
    assert body["results"][0]["exception_flags"] == ["outside_geofence"]
    assert body["results"][0]["reviews"] == []


def test_exceptions_list_contains_only_sessions_pending_review(
    admin_client, flagged_session, client_for, make_employee, job, assign
):
    clean = make_employee(role=Role.WORKER)
    assign(clean, job)
    client_for(clean.user).post(url("clock-in"), event(job), format="json")

    body = admin_client.get(url("staff:exceptions")).json()

    assert [s["id"] for s in body["results"]] == [flagged_session.pk]


def test_staff_list_filters(admin_client, flagged_session, worker):
    assert admin_client.get(url("staff:list"), {"employee_id": worker.pk}).json()["count"] == 1
    assert admin_client.get(url("staff:list"), {"employee_id": 999}).json()["count"] == 0
    assert admin_client.get(url("staff:list"), {"review_status": "approved"}).json()["count"] == 0
    assert admin_client.get(url("staff:list"), {"review_status": "bogus"}).status_code == 400


def test_leadhand_sees_only_jobs_they_lead(
    leadhand_client, flagged_session, client_for, make_employee, make_job, assign
):
    elsewhere_job = make_job(lead_hand=make_employee(role=Role.LEADHAND))
    outsider = make_employee(role=Role.WORKER)
    assign(outsider, elsewhere_job)
    client_for(outsider.user).post(url("clock-in"), event(elsewhere_job), format="json")

    body = leadhand_client.get(url("staff:list")).json()

    assert [s["id"] for s in body["results"]] == [flagged_session.pk]


def test_workers_cannot_use_staff_endpoints(worker_client, flagged_session):
    for name in ("staff:list", "staff:exceptions", "staff:rejected-events"):
        assert worker_client.get(url(name)).status_code == 403
    assert worker_client.get(url("staff:detail", pk=flagged_session.pk)).status_code == 403


def test_rejected_events_list_shows_synchronisation_exceptions(admin_client, worker_client, job):
    worker_client.post(
        url("sync"), {"events": [{**event(job), "action_type": "clock_out"}]}, format="json"
    )

    body = admin_client.get(url("staff:rejected-events")).json()

    assert body["count"] == 1
    rejected = body["results"][0]
    assert rejected["code"] == "no_open_session"
    assert rejected["source"] == "mobile_offline_sync"
    assert rejected["job"]["job_number"] == "J-100"


# --- Reviewing ----------------------------------------------------------------------


def test_admin_approves_a_flagged_session_with_a_reason(admin_client, flagged_session):
    response = review(admin_client, flagged_session)

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["review_status"] == "approved"
    assert body["reviewed_by"] is not None
    assert body["exception_flags"] == ["outside_geofence"]  # preserved
    [entry] = body["reviews"]
    assert entry["decision"] == "approved"
    assert entry["reason"] == "Checked with the site supervisor."


def test_review_history_is_append_only_and_latest_decision_wins(admin_client, flagged_session):
    review(admin_client, flagged_session, "approved", "Looked fine at first.")
    response = review(admin_client, flagged_session, "rejected", "Photos show he was off site.")

    body = response.json()
    assert body["review_status"] == "rejected"
    assert [r["decision"] for r in body["reviews"]] == ["rejected", "approved"]
    assert WorkSessionReview.objects.filter(session=flagged_session).count() == 2
    flagged_session.refresh_from_db()
    latest = flagged_session.reviews.first()
    assert flagged_session.reviewed_at == latest.reviewed_at
    assert flagged_session.reviewed_by == latest.reviewed_by


def test_reviews_cannot_be_edited_or_deleted(admin_client, flagged_session):
    review(admin_client, flagged_session)
    entry = WorkSessionReview.objects.get()

    entry.reason = "rewritten"
    with pytest.raises(ValueError, match="append-only"):
        entry.save()
    with pytest.raises(ValueError, match="append-only"):
        entry.delete()


def test_review_never_changes_punches_or_gps_data(admin_client, flagged_session):
    before = list(AttendanceBatch.objects.values().order_by("pk"))
    punches = list(TimePunch.objects.values().order_by("pk"))

    review(admin_client, flagged_session, "rejected", "Outside the site.")

    assert list(AttendanceBatch.objects.values().order_by("pk")) == before
    assert list(TimePunch.objects.values().order_by("pk")) == punches


@pytest.mark.parametrize("reason", ["", "   ", None])
def test_a_reason_is_required(admin_client, flagged_session, reason):
    payload = {"decision": "rejected"}
    if reason is not None:
        payload["reason"] = reason

    response = admin_client.post(url("staff:review", pk=flagged_session.pk), payload, format="json")

    assert response.status_code == 400
    assert "reason" in response.json()["error"]["details"]
    assert not WorkSessionReview.objects.exists()


def test_invalid_decision_is_rejected(admin_client, flagged_session):
    response = review(admin_client, flagged_session, decision="pending")

    assert response.status_code == 400


def test_open_sessions_cannot_be_reviewed(admin_client, worker_client, job):
    response = worker_client.post(url("clock-in"), event(job), format="json")
    session = WorkSession.objects.get(pk=response.json()["results"][0]["session_id"])

    result = review(admin_client, session)

    assert result.status_code == 409
    assert result.json()["error"]["code"] == "session_open"


def test_only_admins_can_review(leadhand_client, flagged_session):
    response = review(leadhand_client, flagged_session)

    assert response.status_code == 403
    flagged_session.refresh_from_db()
    assert flagged_session.review_status == ReviewStatus.PENDING


def test_reviewing_an_unknown_session_is_404(admin_client):
    assert (
        admin_client.post(
            url("staff:review", pk=999999), {"decision": "approved", "reason": "x"}, format="json"
        ).status_code
        == 404
    )


def test_staff_detail_includes_review_history(admin_client, flagged_session):
    review(admin_client, flagged_session)

    body = admin_client.get(url("staff:detail", pk=flagged_session.pk)).json()

    assert len(body["reviews"]) == 1
    assert body["clock_in"]["location"]["status"] == "outside_geofence"
