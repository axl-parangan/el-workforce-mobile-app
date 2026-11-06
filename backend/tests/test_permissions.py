import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIRequestFactory

from apps.accounts.models import Role
from common.permissions import IsAdmin, IsLeadHand, IsLeadHandOrAdmin, IsWorker


def request_for(user):
    request = APIRequestFactory().get("/")
    request.user = user
    return request


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "permission", "expected"),
    [
        (Role.ADMIN, IsAdmin, True),
        (Role.LEADHAND, IsAdmin, False),
        (Role.LEADHAND, IsLeadHand, True),
        (Role.WORKER, IsLeadHand, False),
        (Role.ADMIN, IsLeadHandOrAdmin, True),
        (Role.LEADHAND, IsLeadHandOrAdmin, True),
        (Role.WORKER, IsLeadHandOrAdmin, False),
        (Role.WORKER, IsWorker, True),
    ],
)
def test_role_permissions(make_user, role, permission, expected):
    user = make_user(role=role)

    assert permission().has_permission(request_for(user), view=None) is expected


def test_role_permissions_reject_anonymous_users():
    assert IsLeadHandOrAdmin().has_permission(request_for(AnonymousUser()), view=None) is False
