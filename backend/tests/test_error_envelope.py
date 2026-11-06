import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions
from rest_framework_simplejwt.exceptions import InvalidToken

from common.exceptions import ApplicationError, api_exception_handler


def handle(exc):
    return api_exception_handler(exc, {"view": None, "request": None})


def test_application_error_uses_envelope():
    response = handle(
        ApplicationError(
            "Worker is already clocked in.", code="already_clocked_in", details={"x": 1}
        )
    )

    assert response.status_code == 400
    assert response.data == {
        "error": {
            "code": "already_clocked_in",
            "message": "Worker is already clocked in.",
            "details": {"x": 1},
        }
    }


def test_drf_validation_error_puts_field_errors_in_details():
    response = handle(exceptions.ValidationError({"name": ["This field is required."]}))

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert response.data["error"]["details"] == {"name": ["This field is required."]}


def test_django_validation_error_is_converted():
    response = handle(DjangoValidationError({"name": ["Bad value."]}))

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert response.data["error"]["details"] == {"name": ["Bad value."]}


def test_not_authenticated_keeps_status_and_code():
    response = handle(exceptions.NotAuthenticated())

    assert response.status_code == 401
    assert response.data["error"]["code"] == "not_authenticated"
    assert "details" not in response.data["error"]


def test_http404_is_converted():
    response = handle(Http404())

    assert response.status_code == 404
    assert response.data["error"]["code"] == "not_found"


def test_invalid_jwt_detail_dict_is_flattened():
    response = handle(InvalidToken())

    assert response.status_code == 401
    assert response.data["error"]["code"] == "token_not_valid"
    assert response.data["error"]["message"]


def test_unhandled_exception_returns_generic_500(settings):
    settings.DEBUG = False

    response = handle(RuntimeError("boom"))

    assert response.status_code == 500
    assert response.data == {
        "error": {"code": "server_error", "message": "An unexpected error occurred."}
    }


@pytest.mark.django_db
def test_protected_endpoint_returns_envelope_without_credentials(api_client):
    response = api_client.get("/api/v1/auth/me/")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
