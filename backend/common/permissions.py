"""Reusable, role-based DRF permission classes.

These only answer "does the user hold one of these roles?". Object-level
rules such as "a LeadHand may only clock workers assigned to the same job"
are business rules: they belong in the owning app's services/selectors and
are enforced there, not encoded here. See docs/development/authentication.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.permissions import BasePermission

from apps.accounts.models import Role

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView


class HasRole(BasePermission):
    """Grants access to authenticated users whose role is in ``allowed_roles``."""

    allowed_roles: frozenset[str] = frozenset()

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        return bool(
            user and user.is_authenticated and getattr(user, "role", None) in self.allowed_roles
        )


class IsAdmin(HasRole):
    allowed_roles = frozenset({Role.ADMIN})


class IsLeadHand(HasRole):
    allowed_roles = frozenset({Role.LEADHAND})


class IsLeadHandOrAdmin(HasRole):
    allowed_roles = frozenset({Role.LEADHAND, Role.ADMIN})


class IsWorker(HasRole):
    allowed_roles = frozenset({Role.WORKER})
