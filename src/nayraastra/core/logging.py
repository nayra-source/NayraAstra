"""Logging setup for NAYRAASTRA.

Configures the root ``nayraastra`` logger with:

* A :class:`rich.logging.RichHandler` for console output.
* An optional rotating file handler (plain text or JSON).
* A :class:`ControlCharFilter` that strips ANSI escape sequences and other
  control characters from log records before they reach any handler.
  This is a security measure: tool output is untrusted and must not be
  allowed to manipulate a terminal via embedded escape codes.

The setup is **idempotent**: calling :func:`setup_logging` a second time with
the same or different parameters is safe and will not add duplicate handlers.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import re
from pathlib import Path

from rich.logging import RichHandler

from nayraastra.core.config import LoggingConfig

# ---------------------------------------------------------------------------
# Control-character filter
# ---------------------------------------------------------------------------

# Matches ANSI CSI sequences and bare C0/C1 control characters.
_CONTROL_RE = re.compile(
    r"(\x9B|\x1B\[)[0-?]*[ -/]*[@-~]"  # CSI sequences
    r"|\x1B[@-Z\\-_]"  # Fe escape sequences
    r"|[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]"  # C0 controls (keep \t \n \r)
)

_LOGGER_NAME = "nayraastra"
_FILE_HANDLER_NAME = "nayraastra.file"
_CONSOLE_HANDLER_NAME = "nayraastra.console"


class ControlCharFilter(logging.Filter):
    """Strip ANSI codes and control characters from log record messages.

    Applied to every handler so that neither the console nor log files
    can be manipulated by escape sequences embedded in tool output.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _CONTROL_RE.sub("", str(record.msg))
        # Also sanitise exception text if present.
        if record.exc_text:
            record.exc_text = _CONTROL_RE.sub("", record.exc_text)
        return True


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------


class _JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_setup_done = False


def setup_logging(config: LoggingConfig, log_dir: Path | None = None) -> None:
    """Configure the ``nayraastra`` logger.

    Idempotent: subsequent calls reconfigure handlers in-place rather than
    adding duplicates.

    Parameters
    ----------
    config:
        Validated logging configuration.
    log_dir:
        Directory for the rotating file handler.  Required when
        ``config.file_enabled`` is *True*.  Ignored otherwise.
    """
    global _setup_done  # noqa: PLW0603

    logger = logging.getLogger(_LOGGER_NAME)
    level = getattr(logging, config.level, logging.INFO)
    logger.setLevel(level)

    control_filter = ControlCharFilter()

    # -- Console handler (Rich) -------------------------------------------
    existing_names = {h.name for h in logger.handlers}

    if _CONSOLE_HANDLER_NAME not in existing_names:
        console_handler = RichHandler(
            level=level,
            show_time=True,
            show_path=False,
            markup=False,
            rich_tracebacks=True,
        )
        console_handler.name = _CONSOLE_HANDLER_NAME
        console_handler.addFilter(control_filter)
        logger.addHandler(console_handler)
    else:
        for h in logger.handlers:
            if h.name == _CONSOLE_HANDLER_NAME:
                h.setLevel(level)

    # -- File handler (optional) ------------------------------------------
    if config.file_enabled and log_dir is not None:
        log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        log_path = log_dir / "nayraastra.log"

        if _FILE_HANDLER_NAME not in existing_names:
            file_handler: logging.Handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=10 * 1024 * 1024,  # 10 MiB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.name = _FILE_HANDLER_NAME
            file_handler.setLevel(level)
            file_handler.addFilter(control_filter)

            if config.json_format:
                file_handler.setFormatter(_JsonFormatter())
            else:
                file_handler.setFormatter(
                    logging.Formatter(
                        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                        datefmt="%Y-%m-%dT%H:%M:%S",
                    )
                )
            logger.addHandler(file_handler)

    logger.propagate = False
    _setup_done = True


def reset_logging() -> None:  # pragma: no cover
    """Remove all handlers from the nayraastra logger (test helper)."""
    global _setup_done  # noqa: PLW0603
    logger = logging.getLogger(_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    _setup_done = False
