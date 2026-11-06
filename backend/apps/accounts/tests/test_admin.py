import pytest
from django.urls import reverse

from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client):
    admin = User.objects.create_superuser(email="admin@example.com", password="x")
    client.force_login(admin)
    return client


def test_user_changelist_and_change_pages_render(admin_client):
    user = User.objects.create_user(email="w@example.com")

    assert admin_client.get(reverse("admin:accounts_user_changelist")).status_code == 200
    assert (
        admin_client.get(reverse("admin:accounts_user_change", args=[user.pk])).status_code == 200
    )


def test_admin_can_create_user_with_email_and_role(admin_client):
    response = admin_client.post(
        reverse("admin:accounts_user_add"),
        {
            "email": "New.Lead@Example.com",
            "role": Role.LEADHAND,
            "usable_password": "true",
            "password1": "a-Long-pass-123",
            "password2": "a-Long-pass-123",
        },
    )

    assert response.status_code == 302, response.content
    user = User.objects.get(email="new.lead@example.com")
    assert user.role == Role.LEADHAND
    assert user.check_password("a-Long-pass-123")


def test_admin_rejects_case_variant_duplicate_email(admin_client):
    User.objects.create_user(email="taken@example.com")

    response = admin_client.post(
        reverse("admin:accounts_user_add"),
        {
            "email": "TAKEN@example.com",
            "role": Role.WORKER,
            "usable_password": "false",
        },
    )

    assert response.status_code == 200
    assert User.objects.filter(email__iexact="taken@example.com").count() == 1
