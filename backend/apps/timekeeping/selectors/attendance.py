"""Read-side queries for attendance.

Session start/end instants are not stored on WorkSession: they are the
``captured_at`` of the batches behind its clock-in and clock-out punches.
``with_punch_times`` annotates them so queries and ordering can use them.
"""

from __future__ import annotations

from django.db.models import OuterRef, Prefetch, QuerySet, Subquery

from apps.accounts.models import User
from apps.jobs.models import AssignmentStatus, Job, JobAssignment
from apps.jobs.selectors.scope import attendance_jobs_for
from apps.timekeeping.models import (
    AttendanceBatch,
    AttendanceBatchItem,
    BatchItemResult,
    PunchType,
    ReviewStatus,
    SessionStatus,
    TimePunch,
    WorkSession,
    WorkSessionReview,
)
from apps.workforce.models import Employee


def _punch_time(punch_type: str) -> Subquery:
    return Subquery(
        TimePunch.objects.filter(session=OuterRef("pk"), punch_type=punch_type).values(
            "batch_item__batch__captured_at"
        )[:1]
    )


def with_punch_times(queryset: QuerySet[WorkSession]) -> QuerySet[WorkSession]:
    return queryset.annotate(
        clock_in_at=_punch_time(PunchType.CLOCK_IN),
        clock_out_at=_punch_time(PunchType.CLOCK_OUT),
    )


def sessions_for_display(queryset: QuerySet[WorkSession] | None = None) -> QuerySet[WorkSession]:
    """Sessions with everything the API serializers read, in a fixed number of queries."""
    queryset = WorkSession.objects.all() if queryset is None else queryset
    punches = TimePunch.objects.select_related(
        "batch_item__batch__performed_by", "batch_item__batch__job"
    )
    return with_punch_times(
        queryset.select_related("assignment__employee", "assignment__job", "reviewed_by")
    ).prefetch_related(
        Prefetch("punches", queryset=punches),
        Prefetch("reviews", queryset=WorkSessionReview.objects.select_related("reviewed_by")),
    )


# --- Employee-facing ------------------------------------------------------------


def employee_for_user(user: User) -> Employee | None:
    return Employee.objects.filter(user=user).first()


def open_session_for_employee(employee: Employee) -> WorkSession | None:
    return (
        sessions_for_display(
            WorkSession.objects.filter(
                assignment__employee=employee, session_status=SessionStatus.OPEN
            )
        )
        .order_by("-created_at")
        .first()
    )


def sessions_for_employee(
    employee: Employee,
    *,
    work_date_from=None,
    work_date_to=None,
    job_id: int | None = None,
) -> QuerySet[WorkSession]:
    queryset = WorkSession.objects.filter(assignment__employee=employee)
    return _filter_sessions(
        sessions_for_display(queryset),
        work_date_from=work_date_from,
        work_date_to=work_date_to,
        job_id=job_id,
    ).order_by("-work_date", "-clock_in_at", "-id")


# --- Staff-facing -------------------------------------------------------------------


def staff_sessions_for_user(user: User) -> QuerySet[WorkSession]:
    """Sessions a staff user may see: company-wide, or the jobs they manage as LeadHand."""
    jobs = attendance_jobs_for(user)
    if jobs is None:
        return WorkSession.objects.all()
    return WorkSession.objects.filter(assignment__job__in=jobs)


def staff_session_list(
    user: User,
    *,
    work_date_from=None,
    work_date_to=None,
    job_id: int | None = None,
    employee_id: int | None = None,
    review_status: str | None = None,
    session_status: str | None = None,
    exceptions_only: bool = False,
) -> QuerySet[WorkSession]:
    queryset = staff_sessions_for_user(user)
    if exceptions_only:
        # Sessions waiting for a reviewer: location or synchronisation exceptions.
        queryset = queryset.filter(review_status=ReviewStatus.PENDING)
    if employee_id is not None:
        queryset = queryset.filter(assignment__employee_id=employee_id)
    if review_status:
        queryset = queryset.filter(review_status=review_status)
    if session_status:
        queryset = queryset.filter(session_status=session_status)
    return _filter_sessions(
        sessions_for_display(queryset),
        work_date_from=work_date_from,
        work_date_to=work_date_to,
        job_id=job_id,
    ).order_by("-work_date", "-clock_in_at", "-id")


def staff_rejected_items(
    user: User, *, job_id: int | None = None, employee_id: int | None = None
) -> QuerySet[AttendanceBatchItem]:
    """Rejected attendance events (synchronisation exceptions) visible to a staff user."""
    queryset = AttendanceBatchItem.objects.filter(result_status=BatchItemResult.REJECTED)
    jobs = attendance_jobs_for(user)
    if jobs is not None:
        queryset = queryset.filter(batch__job__in=jobs)
    if job_id is not None:
        queryset = queryset.filter(batch__job_id=job_id)
    if employee_id is not None:
        queryset = queryset.filter(employee_id=employee_id)
    return queryset.select_related("employee", "batch__job", "batch__performed_by").order_by(
        "-batch__captured_at", "-id"
    )


def crew_job_for(user: User, job_id: int) -> Job | None:
    """The job whose crew ``user`` may view, or None (company-wide or a job they manage)."""
    jobs = attendance_jobs_for(user)
    queryset = Job.objects.all() if jobs is None else jobs
    return queryset.filter(pk=job_id).first()


def crew_status(job: Job) -> list[dict]:
    """Employees actively assigned to ``job`` and whether each is clocked in, and where."""
    assignments = (
        JobAssignment.objects.filter(job=job, status=AssignmentStatus.ACTIVE)
        .select_related("employee")
        .order_by("employee__name")
    )
    employee_ids = [assignment.employee_id for assignment in assignments]
    open_sessions = {
        session.assignment.employee_id: session
        for session in with_punch_times(
            WorkSession.objects.filter(
                assignment__employee_id__in=employee_ids, session_status=SessionStatus.OPEN
            ).select_related("assignment__job")
        )
    }
    crew = []
    for assignment in assignments:
        session = open_sessions.get(assignment.employee_id)
        crew.append(
            {
                "employee": assignment.employee,
                "assignment": assignment,
                "open_session": session,
            }
        )
    return crew


def _filter_sessions(queryset, *, work_date_from, work_date_to, job_id):
    if work_date_from is not None:
        queryset = queryset.filter(work_date__gte=work_date_from)
    if work_date_to is not None:
        queryset = queryset.filter(work_date__lte=work_date_to)
    if job_id is not None:
        queryset = queryset.filter(assignment__job_id=job_id)
    return queryset


def batch_with_items(batch_id: int) -> AttendanceBatch:
    return (
        AttendanceBatch.objects.select_related("job", "performed_by")
        .prefetch_related(
            Prefetch(
                "items",
                queryset=AttendanceBatchItem.objects.select_related(
                    "employee", "time_punch"
                ).order_by("employee_id"),
            )
        )
        .get(pk=batch_id)
    )
