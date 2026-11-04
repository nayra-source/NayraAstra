"""SQLite connection factory and transaction context manager.

This module wraps the stdlib ``sqlite3`` module to enforce consistent
connection settings (WAL mode, foreign keys, busy timeout) and to map
``sqlite3.Error`` to :class:`~nayraastra.core.errors.DatabaseError`.

Usage::

    from nayraastra.db.connection import connect, transaction

    conn = connect(Path("my.db"), wal=True, busy_timeout_ms=5000)

    with transaction(conn):
        conn.execute("INSERT INTO ...")
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from nayraastra.core.errors import DatabaseError


def connect(
    db_path: Path,
    *,
    wal: bool = True,
    busy_timeout_ms: int = 5000,
) -> sqlite3.Connection:
    """Open a SQLite connection with standard NAYRAASTRA settings.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  The parent directory must exist.
    wal:
        If *True* (default), set ``PRAGMA journal_mode=WAL``.
    busy_timeout_ms:
        Milliseconds to wait on a locked database before raising an error.

    Returns
    -------
    sqlite3.Connection
        An open connection with ``row_factory=sqlite3.Row``, foreign-key
        enforcement, and WAL mode (if requested).

    Raises
    ------
    DatabaseError
        On any ``sqlite3.Error`` during connection setup.
    """
    try:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        conn.execute("PRAGMA foreign_keys=ON")

        if wal:
            conn.execute("PRAGMA journal_mode=WAL")

        return conn
    except sqlite3.Error as exc:
        raise DatabaseError(
            f"Failed to open database at {db_path}: {exc}",
            details={"db_path": str(db_path)},
        ) from exc


@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    """Context manager that commits on success and rolls back on exception.

    Parameters
    ----------
    conn:
        An open SQLite connection.

    Yields
    ------
    sqlite3.Connection
        The same connection, inside a transaction.

    Raises
    ------
    DatabaseError
        On commit or rollback failures.
    """
    try:
        yield conn
        try:
            conn.commit()
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Transaction commit failed: {exc}",
            ) from exc
    except DatabaseError:
        # Already wrapped; just rollback and re-raise.
        try:
            conn.rollback()
        except sqlite3.Error:
            pass  # Suppress rollback errors – original error is more important.
        raise
    except sqlite3.Error as exc:
        # Wrap raw sqlite3 errors (e.g. IntegrityError during execute) in DatabaseError.
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise DatabaseError(f"Database operation failed: {exc}") from exc
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
