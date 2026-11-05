"""Unit tests for nayraastra.core.errors."""

from __future__ import annotations

import pytest

from nayraastra.core.errors import (
    ConfigError,
    DatabaseError,
    MigrationError,
    NayraastraError,
    NotImplementedPhaseError,
    ValidationFailure,
)


@pytest.mark.unit
class TestNayraastraError:
    def test_message_preserved(self) -> None:
        exc = NayraastraError("something went wrong")
        assert str(exc) == "something went wrong"
        assert exc.message == "something went wrong"

    def test_default_code(self) -> None:
        exc = NayraastraError("msg")
        assert exc.code == "NAYRAASTRA_ERROR"

    def test_custom_code(self) -> None:
        exc = NayraastraError("msg", code="CUSTOM_CODE")
        assert exc.code == "CUSTOM_CODE"

    def test_details_default_empty(self) -> None:
        exc = NayraastraError("msg")
        assert exc.details == {}

    def test_details_preserved(self) -> None:
        exc = NayraastraError("msg", details={"key": "value", "count": 42})
        assert exc.details["key"] == "value"
        assert exc.details["count"] == 42

    def test_is_exception(self) -> None:
        with pytest.raises(NayraastraError):
            raise NayraastraError("test")


@pytest.mark.unit
class TestSubclasses:
    @pytest.mark.parametrize(
        ("cls", "expected_code"),
        [
            (ConfigError, "CONFIG_ERROR"),
            (DatabaseError, "DATABASE_ERROR"),
            (MigrationError, "MIGRATION_ERROR"),
            (ValidationFailure, "VALIDATION_FAILURE"),
            (NotImplementedPhaseError, "NOT_IMPLEMENTED_PHASE"),
        ],
    )
    def test_stable_codes(self, cls: type[NayraastraError], expected_code: str) -> None:
        exc = cls("test message")
        assert exc.code == expected_code

    def test_subclasses_are_nayraastra_errors(self) -> None:
        for cls in (
            ConfigError,
            DatabaseError,
            MigrationError,
            ValidationFailure,
            NotImplementedPhaseError,
        ):
            assert issubclass(cls, NayraastraError)

    def test_code_override_in_subclass(self) -> None:
        exc = ConfigError("bad cfg", code="OVERRIDE")
        assert exc.code == "OVERRIDE"

    def test_details_in_subclass(self) -> None:
        exc = DatabaseError("db fail", details={"path": "test.db"})
        assert exc.details["path"] == "test.db"
