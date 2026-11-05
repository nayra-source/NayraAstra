"""Unit tests for EngagementService and index management."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nayraastra.core.audit.logger import AuditLogger
from nayraastra.core.domain.models import RulesOfEngagement, ScopeEntry
from nayraastra.core.domain.time_id import FrozenClock
from nayraastra.core.domain.types import Intrusiveness, ScopeEntryKind
from nayraastra.core.engagement.index import load_index
from nayraastra.core.engagement.service import EngagementService
from nayraastra.core.errors import ValidationFailure
from nayraastra.db.connection import connect
from nayraastra.db.migrator import migrate
from nayraastra.db.repositories.audit_sink import SqliteAuditSink
from nayraastra.db.repositories.engagement_repo import SqliteEngagementRepository
from nayraastra.db.repositories.scope_repo import SqliteScopeRepository
from nayraastra.runtime import DefaultWorkspaceProvider


@pytest.mark.unit
class TestEngagementService:
    @pytest.fixture()
    def setup_service(self, tmp_path: Path) -> tuple[EngagementService, sqlite3.Connection]:
        db_path = tmp_path / "test.db"
        conn = connect(db_path)
        migrate(conn)

        eng_repo = SqliteEngagementRepository(conn)
        scope_repo = SqliteScopeRepository(conn)
        audit_sink = SqliteAuditSink(conn)
        clock = FrozenClock(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
        audit = AuditLogger(audit_sink, clock)
        ws_provider = DefaultWorkspaceProvider(tmp_path)

        service = EngagementService(
            repo=eng_repo,
            scope_repo=scope_repo,
            audit_logger=audit,
            workspace_provider=ws_provider,
            clock=clock,
            home_dir=tmp_path,
        )
        return service, conn

    def test_create_and_list_engagement(
        self, setup_service: tuple[EngagementService, sqlite3.Connection], tmp_path: Path
    ) -> None:
        service, _ = setup_service
        scope_entries = [
            ScopeEntry(
                id=1,
                engagement_id="placeholder",
                kind=ScopeEntryKind.CIDR,
                value="10.0.0.0/24",
                in_scope=True,
                created_at=datetime.now(UTC),
            )
        ]

        eng = service.create(
            name="Alpha Test",
            client="Corp",
            auth_reference="AUTH-001",
            scope_entries=scope_entries,
        )

        assert eng.id.startswith("alpha-test-")
        assert eng.status == "active"

        # Check listed
        all_eng = service.list()
        assert len(all_eng) == 1
        assert all_eng[0].id == eng.id

        # Check atomic index file created
        index = load_index(tmp_path)
        assert len(index) == 1
        assert index[0].id == eng.id

    def test_mandatory_auth_and_scope_validation(
        self, setup_service: tuple[EngagementService, sqlite3.Connection]
    ) -> None:
        service, _ = setup_service

        # Empty auth reference
        with pytest.raises(ValidationFailure, match="Authorization reference"):
            service.create("Test", "Client", "", scope_entries=[])

        # No in-scope entries
        with pytest.raises(ValidationFailure, match="at least one in-scope"):
            service.create("Test", "Client", "AUTH-123", scope_entries=[])

    def test_closed_engagement_is_read_only(
        self, setup_service: tuple[EngagementService, sqlite3.Connection]
    ) -> None:
        service, _ = setup_service
        scope_entries = [
            ScopeEntry(
                id=1,
                engagement_id="p",
                kind=ScopeEntryKind.IP,
                value="10.0.0.1",
                in_scope=True,
                created_at=datetime.now(UTC),
            )
        ]
        eng = service.create("Eng", "C", "A-1", scope_entries=scope_entries)
        service.close(eng.id)

        # Modifying scope on closed engagement raises
        new_entry = ScopeEntry(
            id=2,
            engagement_id=eng.id,
            kind=ScopeEntryKind.IP,
            value="10.0.0.2",
            in_scope=True,
            created_at=datetime.now(UTC),
        )
        with pytest.raises(ValidationFailure, match="closed engagement"):
            service.add_scope_entry(eng.id, new_entry)

        with pytest.raises(ValidationFailure, match="closed engagement"):
            service.update_roe(eng.id, RulesOfEngagement(max_intrusiveness=Intrusiveness.PASSIVE))

    def test_index_file_corruption_recovery(self, tmp_path: Path) -> None:
        # Corrupt the index file
        idx_path = tmp_path / "engagements.json"
        idx_path.write_text("{ corrupt json ...")

        # Must not crash, returns empty list
        entries = load_index(tmp_path)
        assert entries == []
