"""Domain errors. Each carries a stable machine code and a Russian message
safe to show to the owner (never a secret or a stack trace)."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details or {}


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class Conflict(DomainError):
    status_code = 409
    code = "conflict"


class Forbidden(DomainError):
    status_code = 403
    code = "forbidden"


class Unauthorized(DomainError):
    status_code = 401
    code = "unauthorized"


class Blocked(DomainError):
    """A guard (profit, budget, kill switch, policy) refused the operation."""

    status_code = 422
    code = "blocked"


class IntegrationUnavailable(DomainError):
    """The connected integration does not support this operation."""

    status_code = 501
    code = "integration_unavailable"


class TooManyRequests(DomainError):
    status_code = 429
    code = "rate_limited"
