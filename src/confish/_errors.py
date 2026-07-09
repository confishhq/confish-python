"""Typed exceptions raised by the SDK."""
from __future__ import annotations

from typing import Any


class ConfishError(Exception):
    """Base class for every error the SDK raises."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.body = body


class NetworkError(ConfishError):
    """A transport-level failure (DNS, TCP, TLS, refused connection)."""

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause


class AuthError(ConfishError):
    """HTTP 401 — missing or invalid API key."""


class ForbiddenError(ConfishError):
    """HTTP 403 — API key doesn't match the environment, or application is disabled."""


class NotFoundError(ConfishError):
    """HTTP 404 — the resource doesn't exist (e.g. an unknown feed slug)."""


class ConflictError(ConfishError):
    """HTTP 409 — typically the action is no longer actionable.

    The action consumer silently skips actions that fail to acknowledge with this error.
    """


class ValidationError(ConfishError):
    """HTTP 422 — request body failed validation.

    `errors` maps field paths to lists of human-readable messages, mirroring Laravel's shape.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: Any = None,
        errors: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, body=body)
        self.errors = errors or {}


class RateLimitError(ConfishError):
    """HTTP 429 — rate limit exceeded.

    `retry_after`, `limit`, and `remaining` are populated from response headers when present.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: Any = None,
        retry_after: int | None = None,
        limit: int | None = None,
        remaining: int | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, body=body)
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining


class ServerError(ConfishError):
    """HTTP 5xx — server-side error."""


class WebhookVerificationError(ConfishError):
    """Base class for webhook verification failures raised by :func:`confish.webhook.verify`."""


class WebhookSignatureError(WebhookVerificationError):
    """The webhook signature is missing, malformed, or doesn't match the body."""


class WebhookTimestampError(WebhookVerificationError):
    """The webhook timestamp is outside the allowed tolerance window (possible replay)."""


def error_from_response(status: int, body: Any, headers: dict[str, str]) -> ConfishError:
    message = _message_from_body(body, fallback=f"Request failed ({status})")

    if status == 401:
        return AuthError(message, status_code=status, body=body)
    if status == 403:
        return ForbiddenError(message, status_code=status, body=body)
    if status == 404:
        return NotFoundError(message, status_code=status, body=body)
    if status == 409:
        return ConflictError(message, status_code=status, body=body)
    if status == 422:
        return ValidationError(
            message,
            status_code=status,
            body=body,
            errors=_extract_validation_errors(body),
        )
    if status == 429:
        return RateLimitError(
            message,
            status_code=status,
            body=body,
            retry_after=_parse_int_header(headers.get("retry-after")),
            limit=_parse_int_header(headers.get("x-ratelimit-limit")),
            remaining=_parse_int_header(headers.get("x-ratelimit-remaining")),
        )
    if status >= 500:
        return ServerError(message, status_code=status, body=body)
    return ConfishError(message, status_code=status, body=body)


def _message_from_body(body: Any, *, fallback: str) -> str:
    if isinstance(body, dict):
        for key in ("error", "message"):
            value = body.get(key)
            if isinstance(value, str):
                return value
    return fallback


def _extract_validation_errors(body: Any) -> dict[str, list[str]]:
    if isinstance(body, dict) and isinstance(body.get("errors"), dict):
        return dict(body["errors"])
    return {}


def _parse_int_header(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
