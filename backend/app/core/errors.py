from typing import NoReturn

from pymongo.errors import DuplicateKeyError, PyMongoError


class AppError(Exception):
    def __init__(self, code: str, http_status: int, message: str, details: dict | None = None) -> None:
        self.code = code
        self.http_status = http_status
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Not found") -> None:
        super().__init__("not_found", 404, message)


class UnknownSourceError(AppError):
    def __init__(self, source_name: str) -> None:
        super().__init__("unknown_source", 404, f"Unknown source: {source_name}")


class DuplicateError(AppError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__("duplicate", 409, message, details)


class BelowThresholdError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("below_threshold", 422, message)


class PolicyViolationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("policy_violation", 422, message)


class DependencyUnavailableError(AppError):
    def __init__(self, message: str = "Database is unavailable") -> None:
        super().__init__("dependency_unavailable", 503, message)


def error_body(code: str, message: str, correlation_id: str, details: dict | None = None) -> dict:
    return {"code": code, "message": message, "correlation_id": correlation_id, "details": details or {}}


def raise_for_database(exc: Exception) -> NoReturn:
    """Map driver failures to a safe API error. Duplicate keys are handled by callers."""
    if isinstance(exc, DuplicateKeyError):
        raise exc
    if isinstance(exc, PyMongoError):
        raise DependencyUnavailableError() from exc
    raise exc
