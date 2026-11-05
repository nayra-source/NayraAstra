"""Application path resolution for NAYRAASTRA.

The *application home* directory contains all persistent state: the SQLite
database, logs, user config, and workspaces.  It defaults to
``~/.nayraastra`` but can be overridden with the ``NAYRAASTRA_HOME``
environment variable.

Directory layout under home::

    ~/.nayraastra/
        config.yaml          # user config overrides
        nayraastra.db        # default SQLite database
        logs/                # rotating log files
        workspaces/          # one sub-directory per engagement
            <engagement_id>/
                artifacts/
                raw/

Security note: engagement ids are validated against a strict allowlist to
prevent path traversal attacks.  Never interpolate user-supplied strings into
paths without calling :func:`validate_engagement_id` first.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from nayraastra.core.errors import ValidationFailure

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_HOME = Path.home() / ".nayraastra"
_ENV_VAR = "NAYRAASTRA_HOME"

# Allowlist: printable ASCII, no slashes, no dots at start, bounded length.
_ENGAGEMENT_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


# ---------------------------------------------------------------------------
# Home directory
# ---------------------------------------------------------------------------


def get_home() -> Path:
    """Return the NAYRAASTRA home directory.

    Reads ``NAYRAASTRA_HOME`` from the environment if set; otherwise falls
    back to ``~/.nayraastra``.  The directory is **not** created here; call
    :func:`ensure_home` to create it.
    """
    raw = os.environ.get(_ENV_VAR)
    return Path(raw).expanduser() if raw else _DEFAULT_HOME


def ensure_home() -> Path:
    """Return the home directory, creating it (mode 0o700) if necessary."""
    home = get_home()
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    return home


# ---------------------------------------------------------------------------
# Standard sub-directories
# ---------------------------------------------------------------------------


def get_logs_dir() -> Path:
    """Return the logs directory path (creates it if absent)."""
    logs = ensure_home() / "logs"
    logs.mkdir(mode=0o700, parents=True, exist_ok=True)
    return logs


def get_workspaces_dir() -> Path:
    """Return the workspaces directory path (creates it if absent)."""
    ws = ensure_home() / "workspaces"
    ws.mkdir(mode=0o700, parents=True, exist_ok=True)
    return ws


def get_default_db_path() -> Path:
    """Return the default SQLite database path inside the home directory."""
    return ensure_home() / "nayraastra.db"


# ---------------------------------------------------------------------------
# Per-engagement workspace
# ---------------------------------------------------------------------------


def validate_engagement_id(engagement_id: str) -> None:
    """Validate *engagement_id* against the allowlist pattern.

    Raises
    ------
    ValidationFailure
        If *engagement_id* is empty, too long, contains path separators, or
        any character outside ``[A-Za-z0-9._-]``.
    """
    if not engagement_id:
        raise ValidationFailure(
            "Engagement id must not be empty.",
            details={"engagement_id": engagement_id},
        )
    if not _ENGAGEMENT_ID_RE.fullmatch(engagement_id):
        raise ValidationFailure(
            f"Invalid engagement id {engagement_id!r}. "
            "Only letters, digits, dots, underscores and hyphens are allowed "
            "(1-64 characters).",
            details={"engagement_id": engagement_id},
        )


def get_workspace_dir(engagement_id: str) -> Path:
    """Return the workspace directory for *engagement_id*, creating it.

    Parameters
    ----------
    engagement_id:
        A validated engagement identifier.  Must pass :func:`validate_engagement_id`.

    Returns
    -------
    Path
        Absolute path to ``<home>/workspaces/<engagement_id>/``.

    Raises
    ------
    ValidationFailure
        If *engagement_id* fails validation.
    """
    validate_engagement_id(engagement_id)
    workspace = get_workspaces_dir() / engagement_id
    workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
    (workspace / "artifacts").mkdir(mode=0o700, exist_ok=True)
    (workspace / "raw").mkdir(mode=0o700, exist_ok=True)
    return workspace
