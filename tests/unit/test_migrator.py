"""Unit tests for nayraastra.db.migrator."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nayraastra.core.errors import MigrationError
from nayraastra.db.migrator import current_version, migrate, pending


@pytest.mark.unit
class TestCurrentVersion:
    def test_zero_on_fresh_db(self, temp_db: sqlite3.Connection) -> None:
        assert current_version(temp_db) == 0

    def test_returns_latest_after_migration(self, migrated_db: sqlite3.Connection) -> None:
        ver = current_version(migrated_db)
        assert ver >= 1


@pytest.mark.unit
class TestPending:
    def test_all_pending_on_fresh_db(self, temp_db: sqlite3.Connection) -> None:
        result = pending(temp_db)
        assert len(result) >= 1
        assert result[0][0] == 1  # version 1 is pending

    def test_none_pending_after_migration(self, migrated_db: sqlite3.Connection) -> None:
        result = pending(migrated_db)
        assert result == []

    def test_checksum_tamper_detected(self, tmp_path: Path, temp_db: sqlite3.Connection) -> None:
        """If an applied migration file is modified, pending() should raise."""
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        mig_file = mig_dir / "0001_test.sql"
        mig_file.write_text("CREATE TABLE test_tbl (id INTEGER PRIMARY KEY);\n")
        migrate(temp_db, migrations_dir=mig_dir)
        mig_file.write_text("CREATE TABLE tampered (id INTEGER PRIMARY KEY);\n")
        with pytest.raises(MigrationError, match="[Cc]hecksum"):
            pending(temp_db, migrations_dir=mig_dir)


@pytest.mark.unit
class TestMigrate:
    def test_fresh_db_reaches_latest_version(self, temp_db: sqlite3.Connection) -> None:
        applied = migrate(temp_db)
        assert len(applied) >= 1
        assert current_version(temp_db) >= 1

    def test_re_run_is_noop(self, migrated_db: sqlite3.Connection) -> None:
        applied = migrate(migrated_db)
        assert applied == []

    def test_applied_names_returned(self, temp_db: sqlite3.Connection) -> None:
        applied = migrate(temp_db)
        assert any("initial" in name for name in applied)

    def test_checksum_tamper_raises_migration_error(
        self, tmp_path: Path, temp_db: sqlite3.Connection
    ) -> None:
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        mig_file = mig_dir / "0001_test.sql"
        mig_file.write_text("CREATE TABLE tbl (id INTEGER PRIMARY KEY);\n")
        migrate(temp_db, migrations_dir=mig_dir)
        mig_file.write_text("DROP TABLE tbl;\n")
        with pytest.raises(MigrationError, match="[Cc]hecksum"):
            migrate(temp_db, migrations_dir=mig_dir)

    def test_all_expected_tables_created(self, migrated_db: sqlite3.Connection) -> None:
        expected_tables = {
            "engagements",
            "scope_entries",
            "hosts",
            "tasks",
            "artifacts",
            "observations",
            "findings",
            "finding_evidence",
            "workflow_runs",
            "audit_log",
        }
        rows = migrated_db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        created = {r["name"] for r in rows}
        assert expected_tables.issubset(created)

    def test_audit_log_update_blocked(self, migrated_db: sqlite3.Connection) -> None:
        migrated_db.execute(
            "INSERT INTO audit_log (event_type, actor, entity_type, entity_id, payload, logged_at)"
            " VALUES ('test.event', 'pytest', 'task', '1', '{}', '2024-01-01T00:00:00Z')"
        )
        migrated_db.commit()
        with pytest.raises((sqlite3.OperationalError, sqlite3.IntegrityError)):
            migrated_db.execute("UPDATE audit_log SET actor='hacker' WHERE id=1")
            migrated_db.commit()

    def test_audit_log_delete_blocked(self, migrated_db: sqlite3.Connection) -> None:
        migrated_db.execute(
            "INSERT INTO audit_log (event_type, actor, entity_type, entity_id, payload, logged_at)"
            " VALUES ('test.del', 'pytest', 'task', '2', '{}', '2024-01-01T00:00:00Z')"
        )
        migrated_db.commit()
        with pytest.raises((sqlite3.OperationalError, sqlite3.IntegrityError)):
            migrated_db.execute("DELETE FROM audit_log WHERE id=1")
            migrated_db.commit()

    def test_task_status_check_constraint(self, migrated_db: sqlite3.Connection) -> None:
        migrated_db.execute(
            "INSERT INTO engagements (id, name, created_at, updated_at)"
            " VALUES ('eng1', 'Test Eng', '2024-01-01T00:00:00Z', '2024-01-01T00:00:00Z')"
        )
        migrated_db.commit()
        with pytest.raises(sqlite3.IntegrityError):
            migrated_db.execute(
                "INSERT INTO tasks (engagement_id, module_name, adapter_name, status, created_at)"
                " VALUES ('eng1', 'mod', 'adp', 'INVALID_STATUS', '2024-01-01T00:00:00Z')"
            )
            migrated_db.commit()

    def test_finding_severity_check_constraint(self, migrated_db: sqlite3.Connection) -> None:
        migrated_db.execute(
            "INSERT INTO engagements (id, name, created_at, updated_at)"
            " VALUES ('eng2', 'Test Eng 2', '2024-01-01T00:00:00Z', '2024-01-01T00:00:00Z')"
        )
        migrated_db.commit()
        with pytest.raises(sqlite3.IntegrityError):
            migrated_db.execute(
                "INSERT INTO findings"
                " (engagement_id, title, severity, confidence, status, created_at, updated_at)"
                " VALUES ('eng2', 'Test', 'MEGA', 'confirmed', 'new',"
                " '2024-01-01T00:00:00Z', '2024-01-01T00:00:00Z')"
            )
            migrated_db.commit()

    def test_foreign_key_constraint_enforced(self, migrated_db: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            migrated_db.execute(
                "INSERT INTO scope_entries (engagement_id, entry_type, value, created_at)"
                " VALUES ('nonexistent-eng', 'allow', '10.0.0.0/8', '2024-01-01T00:00:00Z')"
            )
            migrated_db.commit()

    def test_invalid_migration_filename_raises(
        self, tmp_path: Path, temp_db: sqlite3.Connection
    ) -> None:
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        (mig_dir / "bad_name.sql").write_text("SELECT 1;")
        with pytest.raises(MigrationError):
            migrate(temp_db, migrations_dir=mig_dir)
