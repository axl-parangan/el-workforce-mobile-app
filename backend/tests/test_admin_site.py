"""The Django admin is superuser-only, whatever the application role or staff flag."""

import pytest

from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db


def admin_index_status(client, user) -> int:
    client.force_login(user)
    return client.get("/admin/").status_code


def test_superuser_can_use_the_django_admin(client):
    superuser = User.objects.create_superuser(email="root@example.com", password="x")

    assert admin_index_status(client, superuser) == 200


@pytest.mark.parametrize("role", Role.values)
def test_staff_users_without_superuser_are_refused(client, make_user, role):
    user = make_user(role=role)
    user.is_staff = True  # staff status alone is not enough
    user.save()

    assert admin_index_status(client, user) == 302  # redirected to the admin login


@pytest.mark.parametrize("role", [Role.ADMIN, Role.MANAGER])
def test_admin_and_manager_roles_do_not_grant_django_admin(client, make_user, role):
    assert admin_index_status(client, make_user(role=role)) == 302
