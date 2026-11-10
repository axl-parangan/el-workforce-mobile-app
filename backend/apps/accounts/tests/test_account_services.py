"""Guarded account provisioning and management (ADR 011)."""

from decimal import Decimal

import pytest

from apps.accounts.models import Role, User
from apps.accounts.services.accounts import (
    AccountManagementForbiddenError,
    AccountValidationError,
    create_account,
    update_account,
)
from apps.workforce.models import Employee

pytestmark = pytest.mark.django_db


@pytest.fixture
def actor(make_employee):
    def _actor(role, *, superuser=False):
        user = make_employee(role=role).user
        if superuser:
            user.is_superuser = True
            user.save()
        return user

    return _actor


def new_account(actor_user, role, email="new@example.com", **extra):
    return create_account(
        actor=actor_user,
        email=email,
        role=role,
        employee_name="New Person",
        hourly_rate=Decimal("24.50"),
        **extra,
    )


# --- Creating accounts ------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.LEADHAND, Role.WORKER])
def test_manager_creates_leadhand_and_employee_accounts(actor, role):
    user = new_account(actor(Role.MANAGER), role)

    assert user.role == role
    assert user.employee.name == "New Person"  # every account has an Employee record
    assert user.employee.hourly_rate == Decimal("24.50")
    assert not user.has_usable_password()  # set later through the password-set link
    assert not user.is_staff
    assert not user.is_superuser


@pytest.mark.parametrize("role", [Role.MANAGER, Role.ADMIN])
def test_manager_cannot_create_managers_or_admins(actor, role):
    with pytest.raises(AccountManagementForbiddenError) as exc_info:
        new_account(actor(Role.MANAGER), role)

    assert exc_info.value.code == "role_not_assignable"
    assert not User.objects.filter(email="new@example.com").exists()
    assert not Employee.objects.filter(name="New Person").exists()


def test_admin_creates_managers_but_not_admins(actor):
    admin = actor(Role.ADMIN)

    assert new_account(admin, Role.MANAGER).role == Role.MANAGER
    with pytest.raises(AccountManagementForbiddenError):
        new_account(admin, Role.ADMIN, email="admin2@example.com")


def test_only_a_superuser_creates_admin_accounts(actor):
    user = new_account(actor(Role.ADMIN, superuser=True), Role.ADMIN)

    assert user.role == Role.ADMIN
    assert not user.is_superuser  # a role never implies superuser access
    assert user.employee is not None


@pytest.mark.parametrize("role", [Role.LEADHAND, Role.WORKER])
def test_leadhands_and_employees_cannot_create_accounts(actor, role):
    with pytest.raises(AccountManagementForbiddenError):
        new_account(actor(role), Role.WORKER)


def test_existing_employee_without_a_login_gets_an_account(actor, make_employee):
    employee = make_employee(role=None, name="Field Hand")

    user = create_account(
        actor=actor(Role.MANAGER), email="field@example.com", role=Role.WORKER, employee=employee
    )

    employee.refresh_from_db()
    assert employee.user == user


def test_employee_who_already_has_an_account_is_refused(actor, make_employee):
    with pytest.raises(AccountValidationError):
        create_account(
            actor=actor(Role.MANAGER),
            email="x@example.com",
            role=Role.WORKER,
            employee=make_employee(role=Role.WORKER),
        )


def test_duplicate_email_is_refused_case_insensitively(actor, make_user):
    make_user(email="taken@example.com")

    with pytest.raises(AccountValidationError):
        new_account(actor(Role.MANAGER), Role.WORKER, email="TAKEN@example.com")


def test_new_employee_record_needs_a_rate(actor):
    with pytest.raises(AccountValidationError):
        create_account(
            actor=actor(Role.MANAGER), email="x@example.com", role=Role.WORKER, employee_name="X"
        )


def test_unknown_role_is_refused(actor):
    with pytest.raises(AccountValidationError):
        new_account(actor(Role.ADMIN, superuser=True), "owner")


# --- Managing existing accounts ----------------------------------------------------


@pytest.mark.parametrize("role", [Role.LEADHAND, Role.WORKER])
def test_manager_updates_and_deactivates_staff_accounts(actor, make_user, role):
    target = make_user(role=role)

    update_account(actor=actor(Role.MANAGER), user=target, first_name="Renamed", is_active=False)

    target.refresh_from_db()
    assert target.first_name == "Renamed"
    assert target.is_active is False
    assert target.role == role


@pytest.mark.parametrize("role", [Role.MANAGER, Role.ADMIN])
def test_manager_cannot_modify_managers_or_admins(actor, make_user, role):
    target = make_user(role=role)

    with pytest.raises(AccountManagementForbiddenError):
        update_account(actor=actor(Role.MANAGER), user=target, is_active=False)

    target.refresh_from_db()
    assert target.is_active is True


def test_nobody_manages_their_own_account_here(actor):
    manager = actor(Role.MANAGER)

    with pytest.raises(AccountManagementForbiddenError) as exc_info:
        update_account(actor=manager, user=manager, first_name="Me")

    assert exc_info.value.code == "cannot_manage_own_account"


def test_admin_cannot_touch_a_superuser_account(actor, make_user):
    superuser = make_user(role=Role.WORKER)
    superuser.is_superuser = True
    superuser.save()

    with pytest.raises(AccountManagementForbiddenError):
        update_account(actor=actor(Role.ADMIN), user=superuser, is_active=False)


def test_roles_and_privileges_cannot_be_changed_through_update(actor, make_user):
    target = make_user(role=Role.WORKER)

    for forbidden in ({"role": Role.ADMIN}, {"is_superuser": True}, {"is_staff": True}):
        with pytest.raises(TypeError):
            update_account(actor=actor(Role.ADMIN), user=target, **forbidden)


def test_email_change_rejects_existing_addresses(actor, make_user):
    make_user(email="taken@example.com")
    target = make_user(role=Role.WORKER)

    with pytest.raises(AccountValidationError):
        update_account(actor=actor(Role.MANAGER), user=target, email="Taken@Example.com")
