import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.accounts.models import Role

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_custom_user_model_is_active():
    assert User._meta.label == "accounts.User"
    assert User.USERNAME_FIELD == "email"


def test_new_users_default_to_worker_role():
    user = User.objects.create_user(email="w@example.com", password="x")

    assert user.role == Role.WORKER
    assert user.is_worker


def test_superusers_default_to_admin_role():
    user = User.objects.create_superuser(email="root@example.com", password="x")

    assert user.role == Role.ADMIN
    assert user.is_admin_role
    assert user.is_staff
    assert user.is_superuser


def test_email_is_required():
    with pytest.raises(ValueError, match="email"):
        User.objects.create_user(email="", password="x")


def test_email_is_normalized_to_lowercase():
    user = User.objects.create_user(email="  Jane.Doe@Example.COM ", password="x")

    assert user.email == "jane.doe@example.com"


def test_email_is_unique_case_insensitively():
    User.objects.create_user(email="dup@example.com", password="x")

    with pytest.raises(IntegrityError):
        User.objects.create_user(email="DUP@example.com", password="x")


def test_case_variant_inserted_without_save_is_blocked_by_constraint():
    User.objects.create_user(email="raw@example.com", password="x")

    with pytest.raises(IntegrityError):
        User.objects.bulk_create([User(email="RAW@example.com")])


def test_user_without_password_cannot_log_in():
    user = User.objects.create_user(email="nopass@example.com")

    assert not user.has_usable_password()
