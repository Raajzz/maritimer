"""Domain exceptions and the API error envelope (API.md §0)."""
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework import status
from rest_framework.response import Response


class DomainError(drf_exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "validation_error"
    default_detail = "Invalid request."

    def __init__(self, message=None, details=None, code=None):
        self.message = message or self.default_detail
        self.details = details or {}
        self.error_code = code or self.default_code
        super().__init__(detail=self.message, code=self.error_code)


class ValidationFailed(DomainError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "validation_error"


class InvalidTransition(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "invalid_transition"
    default_detail = "This action is not allowed in the current state."


class Conflict(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_detail = "Conflict."


class PolicyDenied(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "policy_denied"
    default_detail = "This request direction is not allowed."


class Forbidden(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "forbidden"
    default_detail = "You do not have permission to perform this action."


class NotFound(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "not_found"
    default_detail = "Not found."


class NotApproved(drf_exceptions.PermissionDenied):
    default_code = "not_approved"
    default_detail = "Your account is not approved yet."

    def __init__(self, user_status, next_step):
        self.details = {"status": user_status, "next_step": next_step}
        super().__init__(detail=self.default_detail, code="not_approved")


_DRF_CODES = {
    drf_exceptions.NotAuthenticated: "unauthenticated",
    drf_exceptions.AuthenticationFailed: "unauthenticated",
    drf_exceptions.PermissionDenied: "forbidden",
    drf_exceptions.NotFound: "not_found",
    drf_exceptions.ValidationError: "validation_error",
    drf_exceptions.Throttled: "rate_limited",
    drf_exceptions.MethodNotAllowed: "method_not_allowed",
    drf_exceptions.ParseError: "validation_error",
    drf_exceptions.UnsupportedMediaType: "validation_error",
}


def _envelope(code, message, details=None, http_status=400):
    return Response({"error": {"code": code, "message": message, "details": details or {}}}, status=http_status)


def exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return _envelope(exc.error_code, exc.message, exc.details, exc.status_code)
    if isinstance(exc, NotApproved):
        return _envelope("not_approved", str(exc.detail), exc.details, 403)
    if isinstance(exc, Http404):
        return _envelope("not_found", "Not found.", None, 404)
    if isinstance(exc, DjangoPermissionDenied):
        return _envelope("forbidden", "You do not have permission to perform this action.", None, 403)
    if isinstance(exc, DjangoValidationError):
        details = exc.message_dict if hasattr(exc, "error_dict") else {"non_field_errors": exc.messages}
        return _envelope("validation_error", "Invalid input.", details, 400)
    if isinstance(exc, IntegrityError):
        return _envelope("conflict", "The change conflicts with existing data.", {"db": str(exc).splitlines()[0]}, 409)

    from rest_framework.views import exception_handler as drf_exception_handler

    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    code = "error"
    for cls, mapped in _DRF_CODES.items():
        if isinstance(exc, cls):
            code = mapped
            break
    if isinstance(exc, drf_exceptions.ValidationError):
        details = response.data if isinstance(response.data, dict) else {"non_field_errors": response.data}
        return _envelope(code, "Invalid input.", details, response.status_code)
    message = response.data.get("detail", str(exc)) if isinstance(response.data, dict) else str(exc)
    return _envelope(code, str(message), None, response.status_code)
