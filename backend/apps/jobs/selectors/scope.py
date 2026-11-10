"""Which jobs and crews a user may act on (object-level scope, ADR 011).

The single definition of "jobs a LeadHand manages" and "a LeadHand's crew",
shared by timekeeping today and the jobs API later.

A LeadHand manages a job only when BOTH hold (confirmed 2026-11-10):
- the job's ``lead_hand`` is the LeadHand's employee record, and
- the LeadHand has an ACTIVE JobAssignment on that job.
Their crew is everyone with an active assignment on a job they manage.

Managers and Admins act company-wide through capabilities (``*_ANY``); these
selectors only narrow access for crew-scoped users.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.authorization import Capability, has_capability
from apps.accounts.models import User
from apps.jobs.models import AssignmentStatus, Job, JobAssignment


def managed_jobs(user: User) -> QuerySet[Job]:
    """Jobs ``user`` manages as LeadHand (both conditions above)."""
    if not has_capability(user, Capability.JOBS_LEAD):
        return Job.objects.none()
    return Job.objects.filter(
        lead_hand__user=user,
        assignments__employee__user=user,
        assignments__status=AssignmentStatus.ACTIVE,
    ).distinct()


def manages_job(user: User, job: Job) -> bool:
    return managed_jobs(user).filter(pk=job.pk).exists()


def crew_assignments(user: User) -> QuerySet[JobAssignment]:
    """Active assignments on the jobs ``user`` manages."""
    return JobAssignment.objects.filter(job__in=managed_jobs(user), status=AssignmentStatus.ACTIVE)


def assigned_jobs(user: User) -> QuerySet[Job]:
    """Jobs where the user's own employee record has an active assignment."""
    return Job.objects.filter(
        assignments__employee__user=user, assignments__status=AssignmentStatus.ACTIVE
    ).distinct()


def jobs_visible_to(user: User) -> QuerySet[Job]:
    """Jobs a user may see: all (company-wide) or their assigned jobs."""
    if has_capability(user, Capability.JOBS_VIEW_ANY):
        return Job.objects.all()
    if has_capability(user, Capability.JOBS_VIEW_ASSIGNED):
        return assigned_jobs(user)
    return Job.objects.none()


def attendance_jobs_for(user: User) -> QuerySet[Job] | None:
    """Jobs whose attendance ``user`` may view as staff.

    Returns None for company-wide access (no job filter needed), a queryset
    of managed jobs for LeadHands, and an empty queryset otherwise.
    """
    if has_capability(user, Capability.ATTENDANCE_VIEW_ANY):
        return None
    if has_capability(user, Capability.ATTENDANCE_VIEW_CREW):
        return managed_jobs(user)
    return Job.objects.none()


def can_record_attendance_for_others(user: User, job: Job) -> bool:
    """May ``user`` punch other employees on ``job``? Company-wide, or a job they manage."""
    if has_capability(user, Capability.ATTENDANCE_RECORD_ANY):
        return True
    return has_capability(user, Capability.ATTENDANCE_RECORD_CREW) and manages_job(user, job)
