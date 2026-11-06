"""Migration 0002 must preserve existing data and backfill the new columns."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("timekeeping", "0001_initial")]
AFTER = [("timekeeping", "0002_session_reviews_exception_flags_result_codes")]


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


@pytest.mark.django_db(transaction=True)
def test_backfill_preserves_rows_and_derives_codes_and_flags():
    old = migrate(BEFORE)
    try:
        User = old.get_model("accounts", "User")
        Employee = old.get_model("workforce", "Employee")
        Job = old.get_model("jobs", "Job")
        Assignment = old.get_model("jobs", "JobAssignment")
        Batch = old.get_model("timekeeping", "AttendanceBatch")
        Item = old.get_model("timekeeping", "AttendanceBatchItem")
        Session = old.get_model("timekeeping", "WorkSession")
        Punch = old.get_model("timekeeping", "TimePunch")

        user = User.objects.create(email="legacy@example.com", password="x", role="leadhand")
        employee = Employee.objects.create(name="Legacy", hourly_rate=Decimal("20"), user=user)
        job = Job.objects.create(job_number="J-LEGACY", name="Legacy", created_by=user)
        assignment = Assignment.objects.create(employee=employee, job=job, assigned_by=user)
        batch = Batch.objects.create(
            idempotency_key=uuid.uuid4(),
            job=job,
            performed_by=user,
            action_type="clock_in",
            source="mobile_online",
            captured_at=datetime(2026, 3, 10, 12, tzinfo=UTC),
            location_status="outside_geofence",
            location_flags=["outside_geofence", "low_accuracy", "geofence_not_configured"],
        )
        item = Item.objects.create(
            batch=batch,
            employee=employee,
            assignment=assignment,
            result_status="accepted",
            result_message="ok",
            processed_at=datetime(2026, 3, 10, 12, 1, tzinfo=UTC),
        )
        session = Session.objects.create(assignment=assignment, work_date=date(2026, 3, 10))
        Punch.objects.create(session=session, batch_item=item, punch_type="clock_in")

        new = migrate(AFTER)

        migrated_item = new.get_model("timekeeping", "AttendanceBatchItem").objects.get(pk=item.pk)
        assert migrated_item.result_code == "clocked_in"
        assert migrated_item.result_message == "ok"
        migrated_session = new.get_model("timekeeping", "WorkSession").objects.get(pk=session.pk)
        # Only review-relevant flags; geofence_not_configured is informational.
        assert migrated_session.exception_flags == ["low_accuracy", "outside_geofence"]
        assert new.get_model("timekeeping", "TimePunch").objects.count() == 1
        assert new.get_model("timekeeping", "WorkSessionReview").objects.count() == 0
    finally:
        # Leave the schema at the latest migration for the rest of the suite.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
