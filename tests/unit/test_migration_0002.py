"""Unit tests verifying migration from schema version 1 to 2."""

from __future__ import annotations

from pathlib import Path

import pytest

from nayraastra.db.connection import connect
from nayraastra.db.migrator import current_version, migrate


@pytest.mark.unit
class TestMigration0002:
    def test_fresh_db_migrates_to_version_2(self, tmp_path: Path) -> None:
        db_path = tmp_path / "fresh.db"
        conn = connect(db_path)
        applied = migrate(conn)
        assert len(applied) == 2
        assert current_version(conn) == 2

        # Verify new columns exist in audit_log and engagements
        audit_cols = [r["name"] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()]
        assert "prev_hash" in audit_cols
        assert "entry_hash" in audit_cols

        eng_cols = [r["name"] for r in conn.execute("PRAGMA table_info(engagements)").fetchall()]
        assert "client" in eng_cols
        assert "auth_reference" in eng_cols
        assert "roe" in eng_cols

        task_cols = [r["name"] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
        assert "task_uuid" in task_cols
        conn.close()

    def test_existing_v1_db_upgrades_cleanly(self, tmp_path: Path) -> None:
        # Create a v1-only migrations dir
        v1_dir = tmp_path / "v1_migrations"
        v1_dir.mkdir()
        initial_sql = (
            Path(__file__).parent.parent.parent
            / "src"
            / "nayraastra"
            / "db"
            / "migrations"
            / "0001_initial.sql"
        ).read_text(encoding="utf-8")
        (v1_dir / "0001_initial.sql").write_text(initial_sql, encoding="utf-8")

        db_path = tmp_path / "upgrade.db"
        conn = connect(db_path)
        migrate(conn, migrations_dir=v1_dir)
        assert current_version(conn) == 1

        # Insert a sample row into v1 engagement and audit_log
        conn.execute(
            "INSERT INTO engagements (id, name, created_at, updated_at) "
            "VALUES ('legacy-1', 'Legacy Engagement', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO audit_log (event_type, actor, entity_type, entity_id, payload, logged_at) "
            "VALUES ('test.event', 'legacy', 'item', '1', '{}', '2025-01-01T00:00:00Z')"
        )
        conn.commit()

        # Now run full migrator with 0002 present
        applied = migrate(conn)
        assert any("0002" in name for name in applied)
        assert current_version(conn) == 2

        # Verify existing data preserved
        row = conn.execute("SELECT * FROM engagements WHERE id = 'legacy-1'").fetchone()
        assert row["name"] == "Legacy Engagement"
        assert row["client"] == ""  # Default from 0002
        assert row["auth_reference"] == ""

        audit_row = conn.execute("SELECT * FROM audit_log WHERE id = 1").fetchone()
        assert audit_row["actor"] == "legacy"
        assert audit_row["prev_hash"] != ""

        conn.close()
