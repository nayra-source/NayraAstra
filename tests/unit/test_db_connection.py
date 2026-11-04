"""Unit tests for nayraastra.db.connection."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nayraastra.core.errors import DatabaseError
from nayraastra.db.connection import connect, transaction


@pytest.mark.unit
class TestConnect:
    def test_returns_connection(self, tmp_path: Path) -> None:
        conn = connect(tmp_path / "test.db")
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_row_factory_set(self, tmp_path: Path) -> None:
        conn = connect(tmp_path / "test.db")
        assert conn.row_factory is sqlite3.Row
        conn.close()

    def test_foreign_keys_enabled(self, tmp_path: Path) -> None:
        conn = connect(tmp_path / "test.db")
        result = conn.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1
        conn.close()

    def test_wal_mode_enabled(self, tmp_path: Path) -> None:
        conn = connect(tmp_path / "test.db", wal=True)
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"
        conn.close()

    def test_wal_mode_disabled(self, tmp_path: Path) -> None:
        conn = connect(tmp_path / "test.db", wal=False)
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] in ("delete", "rollback")
        conn.close()

    def test_database_error_on_bad_path(self) -> None:
        with pytest.raises(DatabaseError):
            connect(Path("/nonexistent_root_dir/subdir/test.db"))


@pytest.mark.unit
class TestTransaction:
    def test_commits_on_success(self, tmp_path: Path) -> None:
        conn = connect(tmp_path / "test.db")
        conn.execute("CREATE TABLE t (v INTEGER)")
        with transaction(conn):
            conn.execute("INSERT INTO t VALUES (42)")
        # Verify row persists.
        row = conn.execute("SELECT v FROM t").fetchone()
        assert row[0] == 42
        conn.close()

    def test_rolls_back_on_exception(self, tmp_path: Path) -> None:
        conn = connect(tmp_path / "test.db")
        conn.execute("CREATE TABLE t (v INTEGER)")
        conn.commit()
        with pytest.raises(RuntimeError), transaction(conn):
            conn.execute("INSERT INTO t VALUES (99)")
            raise RuntimeError("simulated failure")
        row = conn.execute("SELECT COUNT(*) FROM t").fetchone()
        assert row[0] == 0
        conn.close()

    def test_database_error_re_raised(self, tmp_path: Path) -> None:
        """sqlite3 errors during execute are wrapped in DatabaseError by transaction()."""
        conn = connect(tmp_path / "test.db")
        conn.execute("CREATE TABLE t (v INTEGER NOT NULL)")
        conn.commit()
        with pytest.raises(DatabaseError), transaction(conn):
            conn.execute("INSERT INTO t VALUES (NULL)")
        conn.close()
