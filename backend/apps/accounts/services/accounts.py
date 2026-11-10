"""Guarded account provisioning and management (ADR 011).

Rules (who may manage which roles is defined in authorization.manageable_roles):
- Superusers: any role, including Admin (normally via the superuser-only Django admin).
- Admins: Manager, LeadHand and Employee accounts.
- Managers: LeadHand and Employee accounts only; never other Managers.
- LeadHands and Employees: no account management.
- Nobody manages their own account through these functions, and nobody but a
  superuser can touch a superuser account. ``is_staff``/``is_superuser`` are
  never set here, so these services cannot grant Django admin or superuser access.
- Roles are fixed when the account is created; there is no role-change
  workflow yet (decision D9).

Every account is linked to an Employee record: Admins, Managers and LeadHands
are employees too. New accounts get an unusable password; the password-set
link is sent once email delivery exists (deferred).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework import status

from apps.accounts.authorization import can_manage_role
from apps.accounts.models import Role, User, normalize_email_address
from apps.workforce.models import Employee
from common.exceptions import ApplicationError


class AccountManagementForbiddenError(ApplicationError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "account_management_forbidden"


class AccountValidationError(ApplicationError):
    default_code = "validation_error"


def create_account(
    *,
    actor: User,
    email: str,
    role: str,
    first_name: str = "",
    last_name: str = "",
    employee: Employee | None = None,
    employee_name: str | None = None,
    hourly_rate: Decimal | None = None,
    employee_number: str | None = None,
) -> User:
    """Create a login for a new or existing employee, with a role ``actor`` may assign.

    Pass ``employee`` to give an existing employee (without a login) an account,
    or ``employee_name`` and ``hourly_rate`` to create the employee record too.
    """
    if role not in Role.values:
        raise AccountValidationError("Unknown role.", details={"role": [f"Unknown role {role!r}."]})
    if not can_manage_role(actor, role):
        raise AccountManagementForbiddenError(
            f"You cannot create {Role(role).label} accounts.", code="role_not_assignable"
        )

    email = normalize_email_address(email)
    if User.objects.filter(email=email).exists():
        raise AccountValidationError(
            "An account with this email already exists.",
            details={"email": ["An account with this email already exists."]},
        )

    with transaction.atomic():
        if employee is not None:
            employee = Employee.objects.select_for_update().get(pk=employee.pk)
            if employee.user_id is not None:
                raise AccountValidationError(
                    "This employee already has an account.",
                    details={"employee": ["This employee already has an account."]},
                )
        else:
            name = (employee_name or f"{first_name} {last_name}").strip()
            if not name or hourly_rate is None:
                raise AccountValidationError(
                    "A new employee record needs a name and an hourly rate.",
                    details={"employee": ["Provide employee_name and hourly_rate."]},
                )
            employee = Employee.objects.create(
                name=name, hourly_rate=hourly_rate, employee_number=employee_number
            )

        user = User.objects.create_user(
            email=email,
            password=None,  # unusable until the password-set link is used
            role=role,
            first_name=first_name,
            last_name=last_name,
        )
        employee.user = user
        employee.save(update_fields=["user", "updated_at"])
    return user


def update_account(
    *,
    actor: User,
    user: User,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    is_active: bool | None = None,
) -> User:
    """Change another user's basic account details. The role cannot be changed here."""
    _require_can_manage(actor, user)

    fields: list[str] = []
    if first_name is not None:
        user.first_name, fields = first_name, [*fields, "first_name"]
    if last_name is not None:
        user.last_name, fields = last_name, [*fields, "last_name"]
    if email is not None:
        email = normalize_email_address(email)
        if User.objects.filter(email=email).exclude(pk=user.pk).exists():
            raise AccountValidationError(
                "An account with this email already exists.",
                details={"email": ["An account with this email already exists."]},
            )
        user.email, fields = email, [*fields, "email"]
    if is_active is not None:
        user.is_active, fields = is_active, [*fields, "is_active"]
    if fields:
        user.save(update_fields=fields)
    return user


def _require_can_manage(actor: User, user: User) -> None:
    if user.pk == actor.pk:
        raise AccountManagementForbiddenError(
            "You cannot manage your own account here.", code="cannot_manage_own_account"
        )
    if user.is_superuser and not actor.is_superuser:
        raise AccountManagementForbiddenError("You cannot manage this account.")
    if not can_manage_role(actor, user.role):
        raise AccountManagementForbiddenError(
            f"You cannot manage {user.get_role_display()} accounts.", code="role_not_manageable"
        )
