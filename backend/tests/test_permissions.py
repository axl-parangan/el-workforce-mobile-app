"""The central role -> capability map and the DRF classes built on it."""

import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIRequestFactory

from apps.accounts.authorization import (
    ROLE_CAPABILITIES,
    Capability,
    capabilities_for,
    has_capability,
    manageable_roles,
)
from apps.accounts.models import Role, User
from common.permissions import requires

C = Capability

# The approved matrix (ADR 011), written out explicitly so any change is deliberate.
EXPECTED = {
    Role.WORKER: {
        C.ATTENDANCE_RECORD_SELF,
        C.ATTENDANCE_VIEW_OWN,
        C.ATTENDANCE_REQUEST_CORRECTION,
        C.JOBS_VIEW_ASSIGNED,
    },
    Role.LEADHAND: {
        C.ATTENDANCE_RECORD_SELF,
        C.ATTENDANCE_VIEW_OWN,
        C.ATTENDANCE_REQUEST_CORRECTION,
        C.JOBS_VIEW_ASSIGNED,
        C.ATTENDANCE_RECORD_CREW,
        C.ATTENDANCE_VIEW_CREW,
        C.JOBS_LEAD,
        C.JOBS_CREATE,
        C.JOBS_EDIT_MANAGED,
        C.ASSIGNMENTS_VIEW_CREW,
    },
    Role.MANAGER: {
        C.ATTENDANCE_RECORD_SELF,
        C.ATTENDANCE_VIEW_OWN,
        C.ATTENDANCE_REQUEST_CORRECTION,
        C.JOBS_VIEW_ASSIGNED,
        C.ATTENDANCE_RECORD_ANY,
        C.ATTENDANCE_VIEW_ANY,
        C.ATTENDANCE_REVIEW,
        C.JOBS_CREATE,
        C.JOBS_EDIT_ANY,
        C.JOBS_VIEW_ANY,
        C.ASSIGNMENTS_MANAGE,
        C.EMPLOYEES_VIEW_ANY,
        C.ACCOUNTS_MANAGE_STAFF,
    },
}
EXPECTED[Role.ADMIN] = EXPECTED[Role.MANAGER] | {C.ACCOUNTS_MANAGE_MANAGERS}


@pytest.mark.parametrize("role", Role.values)
def test_role_capabilities_match_the_approved_matrix(role):
    assert set(ROLE_CAPABILITIES[role]) == EXPECTED[role]


def test_every_role_has_a_mapping():
    assert set(ROLE_CAPABILITIES) == set(Role.values)


def test_leadhand_is_not_a_junior_manager():
    leadhand = ROLE_CAPABILITIES[Role.LEADHAND]
    for company_wide in (
        C.ATTENDANCE_RECORD_ANY,
        C.ATTENDANCE_VIEW_ANY,
        C.ATTENDANCE_REVIEW,
        C.ASSIGNMENTS_MANAGE,
        C.ACCOUNTS_MANAGE_STAFF,
        C.JOBS_EDIT_ANY,
        C.JOBS_VIEW_ANY,
        C.EMPLOYEES_VIEW_ANY,
    ):
        assert company_wide not in leadhand


def test_managers_cannot_lead_jobs_or_manage_managers():
    assert C.JOBS_LEAD not in ROLE_CAPABILITIES[Role.MANAGER]
    assert C.ACCOUNTS_MANAGE_MANAGERS not in ROLE_CAPABILITIES[Role.MANAGER]


@pytest.mark.django_db
def test_inactive_unknown_and_anonymous_users_have_no_capabilities(make_user):
    inactive = make_user(role=Role.ADMIN)
    inactive.is_active = False
    unknown = User(email="x@example.com", role="contractor")

    assert capabilities_for(inactive) == frozenset()
    assert capabilities_for(unknown) == frozenset()
    assert capabilities_for(AnonymousUser()) == frozenset()
    assert capabilities_for(None) == frozenset()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "superuser", "expected"),
    [
        (Role.WORKER, False, set()),
        (Role.LEADHAND, False, set()),
        (Role.MANAGER, False, {Role.LEADHAND, Role.WORKER}),
        (Role.ADMIN, False, {Role.MANAGER, Role.LEADHAND, Role.WORKER}),
        (Role.ADMIN, True, set(Role.values)),
    ],
)
def test_manageable_roles(make_user, role, superuser, expected):
    user = make_user(role=role)
    user.is_superuser = superuser

    assert set(manageable_roles(user)) == expected


def request_for(user):
    request = APIRequestFactory().get("/")
    request.user = user
    return request


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "expected"),
    [(Role.ADMIN, True), (Role.MANAGER, True), (Role.LEADHAND, True), (Role.WORKER, False)],
)
def test_requires_grants_with_any_listed_capability(make_user, role, expected):
    permission = requires(C.ATTENDANCE_RECORD_ANY, C.ATTENDANCE_RECORD_CREW)()

    assert permission.has_permission(request_for(make_user(role=role)), view=None) is expected


def test_requires_rejects_anonymous_users():
    permission = requires(C.ATTENDANCE_VIEW_OWN)()

    assert permission.has_permission(request_for(AnonymousUser()), view=None) is False


def test_requires_needs_a_capability():
    with pytest.raises(ValueError, match="at least one"):
        requires()


@pytest.mark.django_db
def test_has_capability(make_user):
    assert has_capability(make_user(role=Role.MANAGER), C.ATTENDANCE_REVIEW)
    assert not has_capability(make_user(role=Role.LEADHAND), C.ATTENDANCE_REVIEW)
