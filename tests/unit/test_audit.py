"""Unit tests for audit logging, redaction, hash chaining, and verification."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nayraastra.core.audit.hasher import compute_entry_hash
from nayraastra.core.audit.logger import GENESIS_HASH, AuditLogger
from nayraastra.core.audit.models import AuditEntry, AuditEventType
from nayraastra.core.audit.redaction import redact_data
from nayraastra.core.audit.verifier import verify_chain
from nayraastra.core.domain.time_id import FrozenClock
from nayraastra.db.connection import connect
from nayraastra.db.migrator import migrate
from nayraastra.db.repositories.audit_sink import SqliteAuditSink


@pytest.mark.unit
class TestAuditRedaction:
    def test_redacts_sensitive_keys_case_insensitive(self) -> None:
        payload = {
            "username": "admin",
            "PASSWORD": "plaintext_password",
            "api_key": "secret_key_123",
            "nested": {
                "user_token": "token_abc",
                "credential": {"client_secret": "xyz"},
            },
        }
        cleaned = redact_data(payload)
        assert cleaned["username"] == "admin"
        assert cleaned["PASSWORD"] == "***REDACTED***"
        assert cleaned["api_key"] == "***REDACTED***"
        assert cleaned["nested"]["user_token"] == "***REDACTED***"
        assert cleaned["nested"]["credential"] == "***REDACTED***"

    def test_truncates_oversize_strings(self) -> None:
        long_str = "x" * 1500
        cleaned = redact_data({"output": long_str}, max_len=100)
        assert len(cleaned["output"]) < 200
        assert "truncated" in cleaned["output"]


@pytest.mark.unit
class TestAuditLoggingAndVerification:
    @pytest.fixture()
    def audit_db(self, tmp_path: Path) -> sqlite3.Connection:
        db_path = tmp_path / "audit_test.db"
        conn = connect(db_path)
        migrate(conn)
        return conn

    def test_valid_chain_after_n_entries(self, audit_db: sqlite3.Connection) -> None:
        sink = SqliteAuditSink(audit_db)
        clock = FrozenClock(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
        logger = AuditLogger(sink, clock, default_actor="tester")

        for i in range(5):
            clock.advance(10)
            logger.log(
                event_type=AuditEventType.TASK_STARTED,
                entity_type="task",
                entity_id=f"t-{i}",
                payload={"index": i},
            )

        entries = sink.get_all_entries()
        assert len(entries) == 5
        assert entries[0].prev_hash == GENESIS_HASH
        assert entries[1].prev_hash == entries[0].entry_hash
        assert entries[2].prev_hash == entries[1].entry_hash

        report = verify_chain(entries)
        assert report.valid
        assert report.count == 5

    def test_tamper_detected_by_verifier(self) -> None:
        entries: list[AuditEntry] = []
        prev_h = GENESIS_HASH

        for i in range(3):
            ts = f"2026-01-01T12:00:0{i}Z"
            entry_h = compute_entry_hash(
                logged_at=ts,
                event_type="test.event",
                actor="system",
                entity_type="item",
                entity_id=str(i),
                payload={"val": i},
                prev_hash=prev_h,
            )
            entry = AuditEntry(
                id=i + 1,
                event_type="test.event",
                actor="system",
                entity_type="item",
                entity_id=str(i),
                payload={"val": i},
                logged_at=ts,
                prev_hash=prev_h,
                entry_hash=entry_h,
            )
            entries.append(entry)
            prev_h = entry_h

        # Original is valid
        assert verify_chain(entries).valid

        # Tamper middle entry payload
        tampered_entry = AuditEntry(
            id=entries[1].id,
            event_type=entries[1].event_type,
            actor=entries[1].actor,
            entity_type=entries[1].entity_type,
            entity_id=entries[1].entity_id,
            payload={"val": 99999},  # Modified!
            logged_at=entries[1].logged_at,
            prev_hash=entries[1].prev_hash,
            entry_hash=entries[1].entry_hash,
        )
        tampered_list = [entries[0], tampered_entry, entries[2]]

        report = verify_chain(tampered_list)
        assert not report.valid
        assert report.first_broken_index == 1
        assert "Content tampered" in str(report.error_message)

    def test_audit_triggers_block_mutation(self, audit_db: sqlite3.Connection) -> None:
        sink = SqliteAuditSink(audit_db)
        clock = FrozenClock(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
        logger = AuditLogger(sink, clock, default_actor="tester")

        entry = logger.log(
            event_type=AuditEventType.ENGAGEMENT_CREATED,
            entity_type="engagement",
            entity_id="e-1",
        )

        with pytest.raises((sqlite3.OperationalError, sqlite3.IntegrityError)):
            audit_db.execute("UPDATE audit_log SET actor = 'attacker' WHERE id = ?", (entry.id,))

        with pytest.raises((sqlite3.OperationalError, sqlite3.IntegrityError)):
            audit_db.execute("DELETE FROM audit_log WHERE id = ?", (entry.id,))
