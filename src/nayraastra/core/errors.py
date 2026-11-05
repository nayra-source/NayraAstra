"""Canonical error hierarchy for NAYRAASTRA.

All exceptions raised by NAYRAASTRA code are subclasses of
:class:`NayraastraError`.  Every subclass carries a stable string *code*
so callers can branch on error type without catching the specific class.

Error codes are SCREAMING_SNAKE_CASE and must never be changed once released
(rename the class instead, keeping the old code).
"""

from __future__ import annotations

from typing import Any


class NayraastraError(Exception):
    """Base exception for all NAYRAASTRA errors.

    Parameters
    ----------
    message:
        Human-readable description of the error.
    code:
        Machine-readable stable identifier (defaults to the class-level
        ``default_code``).
    details:
        Optional arbitrary mapping with structured debug information.
    """

    default_code: str = "NAYRAASTRA_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message: str = message
        self.code: str = code if code is not None else self.default_code
        self.details: dict[str, Any] = details or {}

    def __repr__(self) -> str:  # pragma: no cover
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


class ConfigError(NayraastraError):
    """Raised when configuration loading or validation fails."""

    default_code = "CONFIG_ERROR"


class DatabaseError(NayraastraError):
    """Raised when a database operation fails."""

    default_code = "DATABASE_ERROR"


class MigrationError(NayraastraError):
    """Raised when a schema migration cannot be applied.

    Common causes: checksum mismatch on an already-applied migration file,
    or a SQL syntax error in a new migration.
    """

    default_code = "MIGRATION_ERROR"


class ValidationFailure(NayraastraError):
    """Raised when user-supplied input fails validation.

    Use this in preference to letting Pydantic ``ValidationError`` propagate
    across package boundaries.
    """

    default_code = "VALIDATION_FAILURE"


class NotImplementedPhaseError(NayraastraError):
    """Raised when a feature that belongs to a future phase is called.

    This should only appear in placeholder stubs so callers receive a clear
    message rather than a bare ``NotImplementedError``.
    """

    default_code = "NOT_IMPLEMENTED_PHASE"
