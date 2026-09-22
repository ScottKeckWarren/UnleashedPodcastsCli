"""Exception hierarchy, each carrying the exit code the CLI should return."""

from __future__ import annotations

from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    """Documented exit codes. Scripts branch on these instead of parsing output."""

    SUCCESS = 0
    ERROR = 1
    USAGE = 2
    VALIDATION = 3
    AUTH = 4
    NOT_FOUND = 5
    CONFLICT = 6
    RATE_LIMITED = 7
    FORBIDDEN = 8


class UnleashedError(Exception):
    """Base for every error the CLI reports deliberately."""

    exit_code: ExitCode = ExitCode.ERROR


class ManifestError(UnleashedError):
    """A resource manifest is self-contradictory. A bug, not a user mistake."""


class UsageError(UnleashedError):
    """The caller asked for something impossible before any request was made."""

    exit_code = ExitCode.USAGE


class ConfigError(UsageError):
    """Required configuration is missing or blank."""


class ApiError(UnleashedError):
    """The API answered with a status we treat as a failure."""

    def __init__(self, status: int, payload: Any = None, message: str | None = None) -> None:
        self.status = status
        self.payload = payload if isinstance(payload, dict) else {}
        self.message = message or self.payload.get("message") or f"HTTP {status}"
        super().__init__(f"{self.message} (HTTP {status})")


class AuthError(ApiError):
    exit_code = ExitCode.AUTH


class ForbiddenError(ApiError):
    """The token is valid but lacks the ability this route demands."""

    exit_code = ExitCode.FORBIDDEN


class NotFoundError(ApiError):
    exit_code = ExitCode.NOT_FOUND


class ValidationError(ApiError):
    exit_code = ExitCode.VALIDATION

    @property
    def errors(self) -> dict[str, list[str]]:
        """Laravel's field-keyed error envelope, or empty when the body lacked one."""
        errors = self.payload.get("errors")
        return errors if isinstance(errors, dict) else {}


class ConflictError(ApiError):
    exit_code = ExitCode.CONFLICT

    @property
    def uuid(self) -> str | None:
        """The existing record's UUID, which a 409 carries."""
        value = self.payload.get("uuid")
        return value if isinstance(value, str) else None


class RateLimitError(ApiError):
    exit_code = ExitCode.RATE_LIMITED


STATUS_ERRORS: dict[int, type[ApiError]] = {
    401: AuthError,
    403: ForbiddenError,
    404: NotFoundError,
    409: ConflictError,
    422: ValidationError,
    429: RateLimitError,
}


def error_for_status(status: int, payload: Any = None) -> ApiError:
    """Map an HTTP status onto the exception carrying the right exit code."""
    return STATUS_ERRORS.get(status, ApiError)(status, payload)
