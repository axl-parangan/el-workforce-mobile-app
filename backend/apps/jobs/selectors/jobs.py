"""Read-side queries for the jobs API. Visibility always starts from scope.py."""

from __future__ import annotations

from collections.abc import Iterable

from django.db.models import Q, QuerySet

from apps.accounts.models import User
from apps.jobs.models import AssignmentStatus, Job, JobAssignment

from .scope import assignments_visible_to, jobs_visible_to, managed_jobs


def job_list(
    user: User,
    *,
    status: str | None = None,
    search: str | None = None,
    managed_by_me: bool = False,
    assigned_to_me: bool = False,
) -> QuerySet[Job]:
    queryset = jobs_visible_to(user)
    if status:
        queryset = queryset.filter(status=status)
    if search:
        queryset = queryset.filter(Q(job_number__icontains=search) | Q(name__icontains=search))
    if managed_by_me:
        queryset = queryset.filter(pk__in=managed_jobs(user).values("pk"))
    if assigned_to_me:
        queryset = queryset.filter(
            assignments__employee__user=user, assignments__status=AssignmentStatus.ACTIVE
        )
    return for_display(queryset.distinct()).order_by("job_number")


def for_display(queryset: QuerySet[Job]) -> QuerySet[Job]:
    return queryset.select_related("lead_hand", "created_by__employee", "updated_by__employee")


def visible_job(user: User, job_id: int) -> Job | None:
    return for_display(jobs_visible_to(user)).filter(pk=job_id).first()


def viewer_context(user: User, jobs: Iterable[Job]) -> dict:
    """Per-viewer flags for a page of jobs, computed in two queries."""
    job_ids = [job.pk for job in jobs]
    return {
        "managed_job_ids": set(
            managed_jobs(user).filter(pk__in=job_ids).values_list("pk", flat=True)
        ),
        "my_assignment_ids": dict(
            JobAssignment.objects.filter(
                job_id__in=job_ids, employee__user=user, status=AssignmentStatus.ACTIVE
            ).values_list("job_id", "pk")
        ),
        "my_employee_id": getattr(getattr(user, "employee", None), "pk", None),
    }


def assignment_list(
    user: User,
    *,
    job_id: int | None = None,
    employee_id: int | None = None,
    status: str | None = AssignmentStatus.ACTIVE,
    own_only: bool = False,
) -> QuerySet[JobAssignment]:
    """Assignments visible to ``user``. ``status=None`` includes the full history."""
    queryset = assignments_visible_to(user)
    if own_only:
        queryset = queryset.filter(employee__user=user)
    if job_id is not None:
        queryset = queryset.filter(job_id=job_id)
    if employee_id is not None:
        queryset = queryset.filter(employee_id=employee_id)
    if status:
        queryset = queryset.filter(status=status)
    return queryset.select_related("job", "employee", "assigned_by__employee").order_by(
        "-assigned_at", "-pk"
    )
