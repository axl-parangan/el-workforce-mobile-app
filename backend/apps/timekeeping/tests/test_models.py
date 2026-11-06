from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts.models import Role
from apps.timekeeping.models import (
    AttendanceBatchItem,
    BatchItemResult,
    ItemResultCode,
    LocationStatus,
    PunchType,
    ReviewStatus,
    SessionStatus,
    TimePunch,
    WorkSession,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def leadhand(make_employee):
    return make_employee(role=Role.LEADHAND)


@pytest.fixture
def assignment(make_assignment):
    return make_assignment()


def accepted_item(batch, assignment):
    return AttendanceBatchItem.objects.create(
        batch=batch,
        employee=assignment.employee,
        assignment=assignment,
        result_status=BatchItemResult.ACCEPTED,
        result_code=ItemResultCode.CLOCKED_IN,
        processed_at=timezone.now(),
    )


# --- AttendanceBatch ------------------------------------------------------------------


def test_idempotency_key_is_unique(make_batch, assignment, leadhand):
    batch = make_batch(job=assignment.job, performed_by=leadhand.user)

    with pytest.raises(IntegrityError):
        make_batch(
            job=assignment.job,
            performed_by=leadhand.user,
            idempotency_key=batch.idempotency_key,
        )


def test_batch_stores_location_assessment(make_batch, assignment, leadhand):
    batch = make_batch(
        job=assignment.job,
        performed_by=leadhand.user,
        latitude=Decimal("43.643600"),
        longitude=Decimal("-79.387100"),
        accuracy_meters=Decimal("80.00"),
        distance_meters=Decimal("111.20"),
        location_status=LocationStatus.OUTSIDE_GEOFENCE,
        location_flags=[LocationStatus.OUTSIDE_GEOFENCE, LocationStatus.LOW_ACCURACY],
    )
    batch.refresh_from_db()

    assert batch.location_flags == ["outside_geofence", "low_accuracy"]


@pytest.mark.parametrize(
    "fields",
    [
        {"latitude": Decimal("43.6")},  # longitude missing
        {"accuracy_meters": Decimal("5")},  # accuracy without coordinates
        {"distance_meters": Decimal("5")},  # distance without coordinates
        {
            "latitude": Decimal("43.6"),
            "longitude": Decimal("-79.3"),
            "accuracy_meters": Decimal("-1"),
        },
    ],
)
def test_batch_location_constraints(make_batch, assignment, leadhand, fields):
    with pytest.raises(IntegrityError):
        make_batch(job=assignment.job, performed_by=leadhand.user, **fields)


# --- AttendanceBatchItem ----------------------------------------------------------------


def test_group_batch_has_one_item_per_employee(make_batch, make_assignment, leadhand):
    first = make_assignment()
    second = make_assignment(job=first.job)
    batch = make_batch(job=first.job, performed_by=leadhand.user)

    accepted_item(batch, first)
    accepted_item(batch, second)

    assert batch.items.count() == 2
    with pytest.raises(IntegrityError):
        accepted_item(batch, first)


def test_rejected_item_needs_no_assignment(make_batch, assignment, make_employee, leadhand):
    batch = make_batch(job=assignment.job, performed_by=leadhand.user)

    AttendanceBatchItem.objects.create(
        batch=batch,
        employee=make_employee(role=None),
        result_status=BatchItemResult.REJECTED,
        result_code=ItemResultCode.NO_ACTIVE_ASSIGNMENT,
        result_message="Employee is not assigned to this job.",
        processed_at=timezone.now(),
    )


def test_accepted_item_requires_assignment(make_batch, assignment, leadhand):
    batch = make_batch(job=assignment.job, performed_by=leadhand.user)

    with pytest.raises(IntegrityError):
        AttendanceBatchItem.objects.create(
            batch=batch,
            employee=assignment.employee,
            result_status=BatchItemResult.ACCEPTED,
            processed_at=timezone.now(),
        )


# --- WorkSession / TimePunch -----------------------------------------------------------


def test_session_with_clock_in_and_clock_out(make_batch, assignment, leadhand):
    session = WorkSession.objects.create(assignment=assignment, work_date=date(2026, 11, 6))
    clock_in = make_batch(job=assignment.job, performed_by=leadhand.user)
    clock_out = make_batch(
        job=assignment.job, performed_by=leadhand.user, action_type=PunchType.CLOCK_OUT
    )

    TimePunch.objects.create(
        session=session, batch_item=accepted_item(clock_in, assignment), punch_type="clock_in"
    )
    TimePunch.objects.create(
        session=session, batch_item=accepted_item(clock_out, assignment), punch_type="clock_out"
    )

    assert session.punches.count() == 2


def test_session_cannot_have_two_clock_ins(make_batch, assignment, leadhand):
    session = WorkSession.objects.create(assignment=assignment, work_date=date(2026, 11, 6))
    first = accepted_item(make_batch(job=assignment.job, performed_by=leadhand.user), assignment)
    second = accepted_item(make_batch(job=assignment.job, performed_by=leadhand.user), assignment)
    TimePunch.objects.create(session=session, batch_item=first, punch_type="clock_in")

    with pytest.raises(IntegrityError):
        TimePunch.objects.create(session=session, batch_item=second, punch_type="clock_in")


def test_batch_item_generates_at_most_one_punch(make_batch, assignment, leadhand):
    item = accepted_item(make_batch(job=assignment.job, performed_by=leadhand.user), assignment)
    first = WorkSession.objects.create(assignment=assignment, work_date=date(2026, 11, 6))
    TimePunch.objects.create(session=first, batch_item=item, punch_type="clock_in")
    first.session_status = SessionStatus.CLOSED
    first.save()
    second = WorkSession.objects.create(assignment=assignment, work_date=date(2026, 11, 7))

    with pytest.raises(IntegrityError):
        TimePunch.objects.create(session=second, batch_item=item, punch_type="clock_in")


def test_only_one_open_session_per_assignment(assignment):
    WorkSession.objects.create(assignment=assignment, work_date=date(2026, 11, 6))

    with pytest.raises(IntegrityError):
        WorkSession.objects.create(assignment=assignment, work_date=date(2026, 11, 6))


def test_closed_sessions_allow_a_new_open_session(assignment):
    WorkSession.objects.create(
        assignment=assignment, work_date=date(2026, 11, 6), session_status=SessionStatus.CLOSED
    )

    WorkSession.objects.create(assignment=assignment, work_date=date(2026, 11, 6))


def test_review_decision_requires_reviewer(assignment):
    with pytest.raises(IntegrityError):
        WorkSession.objects.create(
            assignment=assignment,
            work_date=date(2026, 11, 6),
            review_status=ReviewStatus.APPROVED,
        )


def test_reviewed_session(assignment, make_user):
    session = WorkSession.objects.create(
        assignment=assignment,
        work_date=date(2026, 11, 6),
        review_status=ReviewStatus.APPROVED,
        reviewed_by=make_user(role=Role.ADMIN),
        reviewed_at=timezone.now(),
    )

    assert session.review_status == ReviewStatus.APPROVED


@pytest.mark.parametrize(
    ("result_status", "result_code"),
    [
        (BatchItemResult.ACCEPTED, ""),
        (BatchItemResult.ACCEPTED, ItemResultCode.NO_OPEN_SESSION),
        (BatchItemResult.REJECTED, ""),
        (BatchItemResult.REJECTED, ItemResultCode.CLOCKED_IN),
    ],
)
def test_result_code_must_match_result_status(
    make_batch, assignment, leadhand, result_status, result_code
):
    batch = make_batch(job=assignment.job, performed_by=leadhand.user)

    with pytest.raises(IntegrityError):
        AttendanceBatchItem.objects.create(
            batch=batch,
            employee=assignment.employee,
            assignment=assignment,
            result_status=result_status,
            result_code=result_code,
            processed_at=timezone.now(),
        )


def test_pending_item_has_no_code(make_batch, assignment, leadhand):
    batch = make_batch(job=assignment.job, performed_by=leadhand.user)

    item = AttendanceBatchItem.objects.create(batch=batch, employee=assignment.employee)

    assert item.result_code == ""


def test_review_reason_cannot_be_blank_in_the_database(assignment, make_user):
    from apps.timekeeping.models import WorkSessionReview

    session = WorkSession.objects.create(
        assignment=assignment, work_date=date(2026, 11, 6), session_status=SessionStatus.CLOSED
    )
    with pytest.raises(IntegrityError):
        WorkSessionReview.objects.create(
            session=session, decision="approved", reason="   ", reviewed_by=make_user()
        )
