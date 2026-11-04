"""Unit tests for nayraastra.core.logging."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from nayraastra.core.config import LoggingConfig
from nayraastra.core.logging import _LOGGER_NAME, ControlCharFilter, setup_logging


def _clear_logger() -> None:
    """Remove all handlers from the nayraastra logger."""
    logger = logging.getLogger(_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


@pytest.fixture(autouse=True)
def reset_logger() -> None:  # type: ignore[return]
    _clear_logger()
    yield  # type: ignore[misc]
    _clear_logger()


@pytest.mark.unit
class TestSetupLogging:
    def test_adds_console_handler(self, tmp_path: Path) -> None:
        cfg = LoggingConfig(level="INFO", file_enabled=False)
        setup_logging(cfg)
        logger = logging.getLogger(_LOGGER_NAME)
        assert len(logger.handlers) >= 1

    def test_idempotent_no_duplicate_handlers(self, tmp_path: Path) -> None:
        cfg = LoggingConfig(level="INFO", file_enabled=False)
        setup_logging(cfg)
        handler_count_1 = len(logging.getLogger(_LOGGER_NAME).handlers)
        setup_logging(cfg)
        handler_count_2 = len(logging.getLogger(_LOGGER_NAME).handlers)
        assert handler_count_1 == handler_count_2

    def test_file_handler_created(self, tmp_path: Path) -> None:
        cfg = LoggingConfig(level="DEBUG", file_enabled=True, json_format=False)
        setup_logging(cfg, log_dir=tmp_path)
        log_file = tmp_path / "nayraastra.log"
        assert log_file.exists()

    def test_json_format_produces_valid_json(self, tmp_path: Path) -> None:
        cfg = LoggingConfig(level="DEBUG", file_enabled=True, json_format=True)
        setup_logging(cfg, log_dir=tmp_path)
        logger = logging.getLogger(_LOGGER_NAME)
        logger.info("test json message")
        log_file = tmp_path / "nayraastra.log"
        content = log_file.read_text()
        lines = [l for l in content.strip().splitlines() if l]
        assert len(lines) >= 1
        parsed = json.loads(lines[0])
        assert "message" in parsed
        assert "level" in parsed

    def test_level_applied(self) -> None:
        cfg = LoggingConfig(level="ERROR", file_enabled=False)
        setup_logging(cfg)
        logger = logging.getLogger(_LOGGER_NAME)
        assert logger.level == logging.ERROR


@pytest.mark.unit
class TestControlCharFilter:
    def _make_record(self, msg: str) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        return record

    def test_strips_ansi_escape(self) -> None:
        f = ControlCharFilter()
        record = self._make_record("\x1b[31mRED TEXT\x1b[0m")
        f.filter(record)
        assert record.msg == "RED TEXT"

    def test_strips_csi_sequence(self) -> None:
        f = ControlCharFilter()
        record = self._make_record("\x9b1;31mColoured\x9b0m")
        f.filter(record)
        assert "Coloured" in record.msg

    def test_strips_control_chars(self) -> None:
        f = ControlCharFilter()
        # \x07 is BEL, \x08 is BS
        record = self._make_record("hello\x07\x08world")
        f.filter(record)
        assert record.msg == "helloworld"

    def test_preserves_newlines_and_tabs(self) -> None:
        f = ControlCharFilter()
        record = self._make_record("line1\nline2\ttabbed")
        f.filter(record)
        assert "\n" in record.msg
        assert "\t" in record.msg

    def test_always_returns_true(self) -> None:
        f = ControlCharFilter()
        record = self._make_record("normal message")
        assert f.filter(record) is True
