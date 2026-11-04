"""Shared pytest fixtures for NAYRAASTRA tests.

All tests must use ``tmp_path`` and ``monkeypatch`` to avoid touching the
real home directory (``~/.nayraastra``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nayraastra.db.connection import connect


@pytest.fixture()
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect NAYRAASTRA_HOME to a temporary directory for the test."""
    home = tmp_path / "nayraastra_home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("NAYRAASTRA_HOME", str(home))
    return home


@pytest.fixture()
def temp_db(tmp_path: Path) -> sqlite3.Connection:
    """Return an open in-memory SQLite connection for fast unit tests."""

    db_path = tmp_path / "test.db"
    return connect(db_path)


@pytest.fixture()
def migrated_db(temp_db: sqlite3.Connection) -> sqlite3.Connection:
    """Return a fully migrated SQLite connection."""
    from nayraastra.db.migrator import migrate

    migrate(temp_db)
    return temp_db
