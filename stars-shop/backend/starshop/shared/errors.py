"""Domain errors. The API layer maps them to JSON responses with a stable
``code`` that the frontends translate into human messages."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    message = "Некорректный запрос"

    def __init__(self, message: str | None = None, *, code: str | None = None, details: Any = None):
        super().__init__(message or self.message)
        if message:
            self.message = message
        if code:
            self.code = code
        self.details = details


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_error"
    message = "Проверьте введённые данные"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Требуется авторизация"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"
    message = "Недостаточно прав"


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    message = "Не найдено"


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    message = "Конфликт состояния"


class InvalidTransition(Conflict):
    code = "invalid_transition"
    message = "Действие недоступно для текущего статуса заказа"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Слишком много запросов. Попробуйте чуть позже"


class ServiceUnavailable(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "Сервис временно недоступен"


class ProviderError(AppError):
    """An external provider (payment or delivery) failed.

    ``retryable`` tells the caller whether repeating the same request is safe
    and might succeed; ``definitely_not_executed`` is true when the provider
    certainly did not perform the operation (e.g. connection refused before
    the request was sent), which matters for non-idempotent deliveries."""

    status_code = 502
    code = "provider_error"
    message = "Платёжный или сервисный провайдер временно недоступен"

    def __init__(
        self,
        message: str | None = None,
        *,
        retryable: bool = True,
        definitely_not_executed: bool = False,
        code: str | None = None,
        details: Any = None,
    ):
        super().__init__(message, code=code, details=details)
        self.retryable = retryable
        self.definitely_not_executed = definitely_not_executed
