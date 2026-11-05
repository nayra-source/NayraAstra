"""Schema migration engine for NAYRAASTRA.

Migrations are plain ``.sql`` files in ``db/migrations/`` named
``NNNN_description.sql`` where ``NNNN`` is a zero-padded integer.  They are
applied in numeric order and each runs inside its own transaction.

The ``schema_version`` table is created automatically on first use and stores:

* ``version``    – the migration number.
* ``name``       – the filename (without the directory prefix).
* ``applied_at`` – ISO-8601 UTC timestamp.
* ``checksum``   – SHA-256 of the file content at the time of application.

If an already-applied migration file is found on disk with a different checksum,
:func:`migrate` raises :class:`~nayraastra.core.errors.MigrationError` to alert
the operator that history has been tampered with.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from nayraastra.core.errors import MigrationError

# Default migrations directory – sibling ``migrations/`` folder.
_MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_CREATE_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    applied_at  TEXT    NOT NULL,
    checksum    TEXT    NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _now_utc() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(_CREATE_VERSION_TABLE)
    conn.commit()


def _list_migration_files(migrations_dir: Path) -> list[tuple[int, str, Path]]:
    """Return sorted list of (version, name, path) for all migration files."""
    files: list[tuple[int, str, Path]] = []
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        name = sql_file.name
        try:
            version = int(name.split("_")[0])
        except (ValueError, IndexError) as exc:
            raise MigrationError(
                f"Migration filename {name!r} does not start with an integer version.",
                details={"file": str(sql_file)},
            ) from exc
        files.append((version, name, sql_file))
    return files


def _applied_versions(conn: sqlite3.Connection) -> dict[int, dict[str, str]]:
    """Return a mapping of version → {name, checksum} for applied migrations."""
    rows = conn.execute(
        "SELECT version, name, checksum FROM schema_version ORDER BY version"
    ).fetchall()
    return {row["version"]: {"name": row["name"], "checksum": row["checksum"]} for row in rows}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def current_version(conn: sqlite3.Connection, migrations_dir: Path = _MIGRATIONS_DIR) -> int:
    """Return the highest applied migration version, or 0 if none applied.

    Parameters
    ----------
    conn:
        An open SQLite connection.
    migrations_dir:
        Directory containing migration ``.sql`` files.
    """
    _ensure_version_table(conn)
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    result = row["v"]
    return int(result) if result is not None else 0


def pending(
    conn: sqlite3.Connection, migrations_dir: Path = _MIGRATIONS_DIR
) -> list[tuple[int, str]]:
    """Return a list of (version, name) for migrations not yet applied.

    Also validates checksums of already-applied migrations.

    Raises
    ------
    MigrationError
        If a previously applied migration file has a changed checksum.
    """
    _ensure_version_table(conn)
    applied = _applied_versions(conn)
    all_files = _list_migration_files(migrations_dir)

    result: list[tuple[int, str]] = []
    for version, name, path in all_files:
        content = path.read_text(encoding="utf-8")
        checksum = _sha256(content)
        if version in applied:
            if applied[version]["checksum"] != checksum:
                raise MigrationError(
                    f"Checksum mismatch for already-applied migration {name!r}. "
                    "The migration file has been modified after it was applied. "
                    "Restore the original file or create a new migration.",
                    details={
                        "version": version,
                        "file": str(path),
                        "expected": applied[version]["checksum"],
                        "actual": checksum,
                    },
                )
        else:
            result.append((version, name))

    return result


def migrate(conn: sqlite3.Connection, migrations_dir: Path = _MIGRATIONS_DIR) -> list[str]:
    """Apply all pending migrations in version order.

    Each migration runs in its own transaction.  On success the
    ``schema_version`` row is inserted atomically with the migration SQL.

    Parameters
    ----------
    conn:
        An open SQLite connection.
    migrations_dir:
        Directory containing migration ``.sql`` files.

    Returns
    -------
    list[str]
        Names of the migrations that were applied (empty if already up to date).

    Raises
    ------
    MigrationError
        On checksum tampering or SQL errors in a migration file.
    """
    _ensure_version_table(conn)
    applied = _applied_versions(conn)
    all_files = _list_migration_files(migrations_dir)
    applied_names: list[str] = []

    for version, name, path in all_files:
        content = path.read_text(encoding="utf-8")
        checksum = _sha256(content)

        if version in applied:
            # Validate checksum of previously applied migration.
            if applied[version]["checksum"] != checksum:
                raise MigrationError(
                    f"Checksum mismatch for already-applied migration {name!r}. "
                    "The migration file has been modified.",
                    details={
                        "version": version,
                        "file": str(path),
                        "expected": applied[version]["checksum"],
                        "actual": checksum,
                    },
                )
            continue  # Already applied and valid.

        # Apply the migration inside a transaction.
        try:
            conn.executescript(content)
            conn.execute(
                "INSERT INTO schema_version (version, name, applied_at, checksum) "
                "VALUES (?, ?, ?, ?)",
                (version, name, _now_utc(), checksum),
            )
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise MigrationError(
                f"Failed to apply migration {name!r}: {exc}",
                details={"version": version, "file": str(path)},
            ) from exc

        applied_names.append(name)

    return applied_names
