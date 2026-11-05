"""Unit tests for SQLite repository implementations."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nayraastra.core.domain.models import (
    ArtifactRecord,
    Engagement,
    Observation,
    RulesOfEngagement,
    ScopeEntry,
    Target,
    Task,
)
from nayraastra.core.domain.types import (
    Capability,
    Intrusiveness,
    ScopeEntryKind,
    TargetKind,
    TaskStatus,
)
from nayraastra.db.connection import connect
from nayraastra.db.migrator import migrate
from nayraastra.db.repositories.artifact_repo import SqliteArtifactRepository
from nayraastra.db.repositories.engagement_repo import SqliteEngagementRepository
from nayraastra.db.repositories.observation_repo import SqliteObservationRepository
from nayraastra.db.repositories.scope_repo import SqliteScopeRepository
from nayraastra.db.repositories.task_repo import SqliteTaskRepository


@pytest.mark.unit
class TestRepositories:
    @pytest.fixture()
    def db_conn(self, tmp_path: Path) -> sqlite3.Connection:
        db_path = tmp_path / "repo_test.db"
        conn = connect(db_path)
        migrate(conn)
        return conn

    def test_engagement_and_scope_repos(self, db_conn: sqlite3.Connection) -> None:
        eng_repo = SqliteEngagementRepository(db_conn)
        scope_repo = SqliteScopeRepository(db_conn)
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

        eng = Engagement(
            id="eng-repo-1",
            name="Repo Test",
            client="Client A",
            auth_reference="AUTH-999",
            status="active",
            created_at=now,
            updated_at=now,
        )
        eng_repo.save(eng)

        fetched = eng_repo.get("eng-repo-1")
        assert fetched is not None
        assert fetched.client == "Client A"
        assert fetched.auth_reference == "AUTH-999"

        # Update ROE
        new_roe = RulesOfEngagement(max_intrusiveness=Intrusiveness.ACTIVE_INTRUSIVE)
        eng_repo.update_roe("eng-repo-1", new_roe, now)
        assert eng_repo.get("eng-repo-1").roe.max_intrusiveness == Intrusiveness.ACTIVE_INTRUSIVE

        # Scope repo
        entry = ScopeEntry(
            id=1,
            engagement_id="eng-repo-1",
            kind=ScopeEntryKind.CIDR,
            value="10.0.0.0/16",
            in_scope=True,
            created_at=now,
        )
        saved_entry = scope_repo.add_entry(entry)
        entries = scope_repo.list_entries("eng-repo-1")
        assert len(entries) == 1
        assert entries[0].value == "10.0.0.0/16"

        # Remove entry
        assert scope_repo.remove_entry(saved_entry.id, "eng-repo-1")
        assert len(scope_repo.list_entries("eng-repo-1")) == 0

    def test_task_artifact_observation_repos(self, db_conn: sqlite3.Connection) -> None:
        eng_repo = SqliteEngagementRepository(db_conn)
        task_repo = SqliteTaskRepository(db_conn)
        art_repo = SqliteArtifactRepository(db_conn)
        obs_repo = SqliteObservationRepository(db_conn)

        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        eng = Engagement(
            id="eng-repo-2",
            name="Repo Test 2",
            client="Client B",
            auth_reference="AUTH-888",
            status="active",
            created_at=now,
            updated_at=now,
        )
        eng_repo.save(eng)

        task = Task(
            id="task-uuid-1",
            engagement_id="eng-repo-2",
            module_name="port_scan",
            adapter_name="fake",
            capability=Capability.PORT_SCAN,
            target=Target(raw="10.0.0.1", normalized="10.0.0.1", kind=TargetKind.IP),
            status=TaskStatus.PENDING,
            created_at=now,
        )
        task_repo.save(task)

        fetched_task = task_repo.get("task-uuid-1")
        assert fetched_task is not None
        assert fetched_task.status == TaskStatus.PENDING

        # Artifact repo
        artifact = ArtifactRecord(
            task_id="task-uuid-1",
            engagement_id="eng-repo-2",
            artifact_type="raw_output",
            mime_type="text/plain",
            path="artifacts/output.txt",
            size_bytes=128,
            sha256="abc123sha",
            created_at=now,
        )
        art_repo.save(artifact)
        artifacts = art_repo.list_by_task("task-uuid-1")
        assert len(artifacts) == 1
        assert artifacts[0].sha256 == "abc123sha"

        # Observation repo
        obs = Observation(
            task_id="task-uuid-1",
            engagement_id="eng-repo-2",
            observation_key="open_port",
            value={"port": 80, "service": "http"},
            confidence="confirmed",
            observed_at=now,
        )
        obs_repo.save(obs)
        observations = obs_repo.list_by_task("task-uuid-1")
        assert len(observations) == 1
        assert observations[0].observation_key == "open_port"
