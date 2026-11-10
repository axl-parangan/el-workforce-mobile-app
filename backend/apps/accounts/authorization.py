"""Role-based authorization: the only place that maps roles to abilities (ADR 011).

Everything else asks ``has_capability(user, Capability.X)`` (or uses the DRF
class ``common.permissions.requires``) instead of comparing role names, so
adding or changing a role is a change to this file alone. A test enforces
that role comparisons do not reappear elsewhere.

Capabilities answer "may this user do this kind of thing at all?". *Which*
records a LeadHand or Employee may touch is decided by scope selectors
(``apps/jobs/selectors/scope.py``) and the owning services.

The mapping is fixed in code. It is shaped so it could later be backed by
Django's Group/Permission tables for runtime editing without touching callers.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from apps.accounts.models import Role

if TYPE_CHECKING:
    from apps.accounts.models import User


class Capability(StrEnum):
    # --- Own records (every role) ----------------------------------------------------
    ATTENDANCE_RECORD_SELF = "attendance.record_self"
    ATTENDANCE_VIEW_OWN = "attendance.view_own"
    # Future correction workflow: an employee asks a Manager/Admin to fix a punch.
    ATTENDANCE_REQUEST_CORRECTION = "attendance.request_correction"
    JOBS_VIEW_ASSIGNED = "jobs.view_assigned"

    # --- Crew: limited to jobs the user manages as LeadHand -------------------------
    ATTENDANCE_RECORD_CREW = "attendance.record_crew"
    ATTENDANCE_VIEW_CREW = "attendance.view_crew"
    # May be set as Job.lead_hand.
    JOBS_LEAD = "jobs.lead"

    # --- Company-wide operations --------------------------------------------------------
    ATTENDANCE_RECORD_ANY = "attendance.record_any"
    ATTENDANCE_VIEW_ANY = "attendance.view_any"
    ATTENDANCE_REVIEW = "attendance.review"
    JOBS_CREATE = "jobs.create"
    JOBS_EDIT = "jobs.edit"
    JOBS_VIEW_ANY = "jobs.view_any"
    ASSIGNMENTS_MANAGE = "assignments.manage"
    # Create and manage LeadHand and Employee accounts.
    ACCOUNTS_MANAGE_STAFF = "accounts.manage_staff"
    # Create and manage Manager accounts.
    ACCOUNTS_MANAGE_MANAGERS = "accounts.manage_managers"


_EMPLOYEE = frozenset(
    {
        Capability.ATTENDANCE_RECORD_SELF,
        Capability.ATTENDANCE_VIEW_OWN,
        Capability.ATTENDANCE_REQUEST_CORRECTION,
        Capability.JOBS_VIEW_ASSIGNED,
    }
)

# LeadHand: an ordinary employee plus crew responsibilities. Not a junior Manager.
_LEADHAND = _EMPLOYEE | {
    Capability.ATTENDANCE_RECORD_CREW,
    Capability.ATTENDANCE_VIEW_CREW,
    Capability.JOBS_LEAD,
    Capability.JOBS_CREATE,
    Capability.JOBS_EDIT,
}

# Manager: company-wide operations. Still an employee who clocks in themselves.
_MANAGER = _EMPLOYEE | {
    Capability.ATTENDANCE_RECORD_ANY,
    Capability.ATTENDANCE_VIEW_ANY,
    Capability.ATTENDANCE_REVIEW,
    Capability.JOBS_CREATE,
    Capability.JOBS_EDIT,
    Capability.JOBS_VIEW_ANY,
    Capability.ASSIGNMENTS_MANAGE,
    Capability.ACCOUNTS_MANAGE_STAFF,
}

# Admin: everything a Manager can do, plus managing Managers.
_ADMIN = _MANAGER | {Capability.ACCOUNTS_MANAGE_MANAGERS}

ROLE_CAPABILITIES: dict[str, frozenset[Capability]] = {
    Role.WORKER: _EMPLOYEE,
    Role.LEADHAND: frozenset(_LEADHAND),
    Role.MANAGER: frozenset(_MANAGER),
    Role.ADMIN: frozenset(_ADMIN),
}


def capabilities_for(user: User | None) -> frozenset[Capability]:
    """All capabilities of an active, authenticated user; empty otherwise or for unknown roles."""
    if user is None or not user.is_authenticated or not user.is_active:
        return frozenset()
    return ROLE_CAPABILITIES.get(getattr(user, "role", None), frozenset())


def has_capability(user: User | None, capability: Capability) -> bool:
    return capability in capabilities_for(user)


def has_any_capability(user: User | None, *capabilities: Capability) -> bool:
    granted = capabilities_for(user)
    return any(capability in granted for capability in capabilities)


def manageable_roles(actor: User | None) -> frozenset[str]:
    """Roles whose accounts ``actor`` may create and manage.

    - Superusers: every role, including Admin.
    - Managers and Admins: Employee and LeadHand accounts.
    - Admins additionally: Manager accounts.
    Admin accounts are superuser-only, so no API user can create or grant Admin.
    """
    if actor is None or not actor.is_authenticated or not actor.is_active:
        return frozenset()
    if actor.is_superuser:
        return frozenset(Role.values)
    roles: set[str] = set()
    if has_capability(actor, Capability.ACCOUNTS_MANAGE_STAFF):
        roles |= {Role.LEADHAND, Role.WORKER}
    if has_capability(actor, Capability.ACCOUNTS_MANAGE_MANAGERS):
        roles.add(Role.MANAGER)
    return frozenset(roles)


def can_manage_role(actor: User | None, role: str) -> bool:
    """May ``actor`` create or manage accounts that hold ``role``?"""
    return role in manageable_roles(actor)
