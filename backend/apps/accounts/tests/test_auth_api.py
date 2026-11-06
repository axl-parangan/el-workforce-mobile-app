import pytest
from django.urls import reverse

from apps.accounts.models import Role

pytestmark = pytest.mark.django_db

# Matches the make_user fixture default.
DEFAULT_PASSWORD = "s3cure-Passw0rd"


def obtain_tokens(api_client, email, password=DEFAULT_PASSWORD):
    response = api_client.post(
        reverse("v1:accounts:token-obtain"), {"email": email, "password": password}
    )
    assert response.status_code == 200, response.content
    return response.json()


def test_obtain_token_pair_and_fetch_current_user(api_client, make_user):
    make_user(email="lead@example.com", role=Role.LEADHAND)
    tokens = obtain_tokens(api_client, "lead@example.com")

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    response = api_client.get(reverse("v1:accounts:me"))

    assert response.status_code == 200
    assert response.json() == {
        "id": response.json()["id"],
        "email": "lead@example.com",
        "first_name": "",
        "last_name": "",
        "role": "leadhand",
    }


def test_login_email_is_case_insensitive(api_client, make_user):
    make_user(email="mixed@example.com")

    obtain_tokens(api_client, "MiXeD@Example.com")


def test_wrong_password_returns_error_envelope(api_client, make_user):
    make_user(email="w1@example.com")

    response = api_client.post(
        reverse("v1:accounts:token-obtain"), {"email": "w1@example.com", "password": "wrong"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "no_active_account"


def test_login_requires_email_field(api_client):
    response = api_client.post(
        reverse("v1:accounts:token-obtain"), {"username": "someone", "password": "x"}
    )

    assert response.status_code == 400
    assert "email" in response.json()["error"]["details"]


def test_inactive_user_cannot_log_in(api_client, make_user):
    user = make_user(email="gone@example.com")
    user.is_active = False
    user.save()

    response = api_client.post(
        reverse("v1:accounts:token-obtain"),
        {"email": "gone@example.com", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 401


def test_refresh_rotates_and_blacklists_old_refresh_token(api_client, make_user):
    make_user(email="w2@example.com")
    tokens = obtain_tokens(api_client, "w2@example.com")
    refresh_url = reverse("v1:accounts:token-refresh")

    first = api_client.post(refresh_url, {"refresh": tokens["refresh"]})
    assert first.status_code == 200
    assert "refresh" in first.json()

    reused = api_client.post(refresh_url, {"refresh": tokens["refresh"]})
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "token_not_valid"


def test_blacklist_endpoint_logs_out_refresh_token(api_client, make_user):
    make_user(email="w3@example.com")
    tokens = obtain_tokens(api_client, "w3@example.com")

    logout = api_client.post(reverse("v1:accounts:token-blacklist"), {"refresh": tokens["refresh"]})
    assert logout.status_code == 200

    response = api_client.post(reverse("v1:accounts:token-refresh"), {"refresh": tokens["refresh"]})
    assert response.status_code == 401
