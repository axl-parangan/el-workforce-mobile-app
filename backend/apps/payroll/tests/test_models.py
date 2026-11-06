from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts.models import Role
from apps.payroll.models import PayrollLine, PayrollRun, PayrollRunStatus
from apps.payroll.services.calculations import calculate_hourly_pay
from apps.timekeeping.models import SessionStatus, WorkSession

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_user(make_user):
    return make_user(role=Role.ADMIN)


@pytest.fixture
def run(admin_user):
    return PayrollRun.objects.create(
        period_start=date(2026, 11, 1), period_end=date(2026, 11, 14), created_by=admin_user
    )


@pytest.fixture
def session(make_assignment):
    return WorkSession.objects.create(
        assignment=make_assignment(),
        work_date=date(2026, 11, 6),
        session_status=SessionStatus.CLOSED,
    )


def line_for(run, session, *, adjustment=Decimal("0.00"), final=None):
    hours, rate = Decimal("7.7500"), Decimal("18.3330")
    gross = calculate_hourly_pay(approved_hours=hours, hourly_rate=rate)
    return PayrollLine.objects.create(
        payroll_run=run,
        session=session,
        hours_paid=hours,
        hourly_rate_applied=rate,
        gross_pay=gross,
        adjustment_amount=adjustment,
        final_amount=gross + adjustment if final is None else final,
    )


def test_line_snapshots_hours_and_rate(run, session):
    line = line_for(run, session, adjustment=Decimal("-2.08"))
    line.refresh_from_db()

    assert line.gross_pay == Decimal("142.08")
    assert line.final_amount == Decimal("140.00")
    assert line.hourly_rate_applied == Decimal("18.3330")


def test_final_amount_must_equal_gross_plus_adjustment(run, session):
    with pytest.raises(IntegrityError):
        line_for(run, session, final=Decimal("999.99"))


def test_a_session_is_paid_at_most_once(run, session, admin_user):
    line_for(run, session)
    other_run = PayrollRun.objects.create(
        period_start=date(2026, 11, 1), period_end=date(2026, 11, 14), created_by=admin_user
    )

    with pytest.raises(IntegrityError):
        line_for(other_run, session)


@pytest.mark.parametrize(
    "fields",
    [
        {"period_end": date(2026, 10, 31)},
        {"status": PayrollRunStatus.APPROVED},  # no approval recorded
        {"paid_at": timezone.now()},  # paid before approval
    ],
)
def test_run_integrity_constraints(admin_user, fields):
    values = {
        "period_start": date(2026, 11, 1),
        "period_end": date(2026, 11, 14),
        "created_by": admin_user,
        **fields,
    }
    with pytest.raises(IntegrityError):
        PayrollRun.objects.create(**values)


def test_approved_and_paid_run(admin_user):
    now = timezone.now()
    run = PayrollRun.objects.create(
        period_start=date(2026, 11, 1),
        period_end=date(2026, 11, 14),
        created_by=admin_user,
        status=PayrollRunStatus.PAID,
        approved_by=admin_user,
        approved_at=now,
        paid_at=now,
    )

    assert run.status == PayrollRunStatus.PAID
