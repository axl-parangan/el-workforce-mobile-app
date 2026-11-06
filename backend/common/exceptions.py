"""Consistent API error responses.

Every error returned by the API uses the same envelope::

    {
        "error": {
            "code": "validation_error",
            "message": "Invalid input.",
            "details": {"field": ["This field is required."]}
        }
    }

- ``code`` is a stable, machine-readable string clients can branch on.
- ``message`` is a human-readable summary.
- ``details`` is optional structured context (e.g. per-field errors).

Services raise ``ApplicationError`` (or a subclass) for business-rule
violations so that they never depend on DRF or HTTP concerns directly.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.serializers import as_serializer_error
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class ApplicationError(Exception):
    """A business-rule violation raised from the service layer.

    Subclasses can override ``status_code`` and ``default_code`` to express
    more specific failures (for example a 409 for a duplicate punch).
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    default_code: str = "application_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.details = details or {}


def _error_response(
    *,
    code: str,
    message: str,
    details: Any = None,
    status_code: int,
    headers: dict[str, str] | None = None,
) -> Response:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details:
        payload["details"] = details
    return Response({"error": payload}, status=status_code, headers=headers)


def _from_api_exception(exc: exceptions.APIException, response: Response) -> Response:
    headers = {
        key: value
        for key, value in response.headers.items()
        if key in ("WWW-Authenticate", "Retry-After")
    }

    if isinstance(exc, exceptions.ValidationError):
        return _error_response(
            code="validation_error",
            message="Invalid input.",
            details=response.data,
            status_code=response.status_code,
            headers=headers,
        )

    data = response.data
    codes = exc.get_codes()
    code = codes if isinstance(codes, str) else str(exc.default_code)

    if isinstance(data, dict) and "detail" in data:
        # DRF wraps string details as {"detail": ...}. Some exceptions (e.g.
        # SimpleJWT's InvalidToken) carry a dict: {"detail", "code", "messages"}.
        extra = {key: value for key, value in data.items() if key not in ("detail", "code")}
        return _error_response(
            code=str(data.get("code") or code),
            message=str(data["detail"]),
            details=extra,
            status_code=response.status_code,
            headers=headers,
        )

    return _error_response(
        code=code,
        message=str(exc.default_detail),
        details=data,
        status_code=response.status_code,
        headers=headers,
    )


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF ``EXCEPTION_HANDLER`` that renders every error in the standard envelope."""
    if isinstance(exc, ApplicationError):
        return _error_response(
            code=exc.code,
            message=exc.message,
            details=exc.details,
            status_code=exc.status_code,
        )

    if isinstance(exc, IntegrityError):
        # A database constraint caught a conflicting write (normally prevented
        # earlier by service rules or locks). Report it as a conflict, not a 500.
        logger.warning("Integrity error in API request: %s", exc)
        return _error_response(
            code="conflict",
            message="The request conflicts with existing data. Refresh and try again.",
            status_code=status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(as_serializer_error(exc))
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(exc, exceptions.APIException):
        return _from_api_exception(exc, response)

    # Unhandled exception. In DEBUG let Django render its technical 500 page.
    if settings.DEBUG:
        return None

    view = context.get("view")
    logger.exception(
        "Unhandled API exception",
        extra={"view": view.__class__.__name__ if view else None},
        exc_info=exc,
    )
    return _error_response(
        code="server_error",
        message="An unexpected error occurred.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
