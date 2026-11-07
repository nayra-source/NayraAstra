"""Composition root and Runtime facade for NAYRAASTRA.

This module is the ONLY layer where core, db, and adapters are wired together.
Upper layers (CLI, workflows, and modules) interact exclusively through Runtime.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from pathlib import Path

from nayraastra.adapters.fake.adapter import FakeAdapter, FakeDisruptiveAdapter
from nayraastra.adapters.nmap import NmapAdapter
from nayraastra.adapters.registry import AdapterRegistry
from nayraastra.core.audit.logger import AuditLogger
from nayraastra.core.audit.verifier import verify_chain
from nayraastra.core.config import AppConfig, load_config
from nayraastra.core.domain.time_id import Clock, IdGenerator, UtcClock, UuidGenerator
from nayraastra.core.engagement.service import EngagementService
from nayraastra.core.errors import ConfigError, NayraastraError, ValidationFailure
from nayraastra.core.events.bus import EventBus
from nayraastra.core.paths import get_home, get_workspace_dir
from nayraastra.core.ports import ToolAdapterPort, WorkspaceProvider
from nayraastra.core.scope.authorizer import TaskAuthorizer
from nayraastra.core.scope.normalize import normalize_target
from nayraastra.core.tasks.scheduler import Scheduler
from nayraastra.core.tasks.service import TaskService
from nayraastra.db.connection import connect
from nayraastra.db.migrator import migrate
from nayraastra.db.repositories.artifact_repo import SqliteArtifactRepository
from nayraastra.db.repositories.audit_sink import SqliteAuditSink
from nayraastra.db.repositories.engagement_repo import SqliteEngagementRepository
from nayraastra.db.repositories.observation_repo import SqliteObservationRepository
from nayraastra.db.repositories.scope_repo import SqliteScopeRepository
from nayraastra.db.repositories.task_repo import SqliteTaskRepository

__all__ = [
    "ConfigError",
    "DefaultWorkspaceProvider",
    "NayraastraError",
    "Runtime",
    "Session",
    "ToolAdapterPort",
    "ValidationFailure",
    "build_runtime",
    "normalize_target",
    "verify_chain",
]


class DefaultWorkspaceProvider:
    """Resolves workspace and database paths for engagements."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = home or get_home()

    def get_workspace_dir(self, engagement_id: str) -> Path:
        ws = get_workspace_dir(engagement_id)
        ws.mkdir(mode=0o700, parents=True, exist_ok=True)
        return ws

    def get_artifacts_dir(self, engagement_id: str) -> Path:
        art = self.get_workspace_dir(engagement_id) / "artifacts"
        art.mkdir(mode=0o700, parents=True, exist_ok=True)
        return art

    def get_logs_dir(self, engagement_id: str) -> Path:
        logs = self.get_workspace_dir(engagement_id) / "logs"
        logs.mkdir(mode=0o700, parents=True, exist_ok=True)
        return logs

    def get_db_path(self, engagement_id: str) -> Path:
        return self.get_workspace_dir(engagement_id) / "nayraastra.db"


class Session:
    """Engagement-bound runtime session interacting with a single engagement database."""

    def __init__(
        self,
        engagement_id: str,
        conn: sqlite3.Connection,
        tasks: TaskService,
        scheduler: Scheduler,
        audit: AuditLogger,
        events: EventBus,
        registry: AdapterRegistry,
    ) -> None:
        self.engagement_id = engagement_id
        self.conn = conn
        self.tasks = tasks
        self.scheduler = scheduler
        self.audit = audit
        self.events = events
        self.registry = registry

    def close(self) -> None:
        """Close engagement database connection."""
        with contextlib.suppress(sqlite3.Error):
            self.conn.close()


class Runtime:
    """Central orchestration facade exposing services to the application."""

    def __init__(
        self,
        config: AppConfig,
        conn: sqlite3.Connection,
        engagements: EngagementService,
        tasks: TaskService,
        scheduler: Scheduler,
        events: EventBus,
        registry: AdapterRegistry,
        audit: AuditLogger,
        workspace_provider: WorkspaceProvider,
        clock: Clock,
        id_gen: IdGenerator,
        authorizer: TaskAuthorizer,
        home: Path,
    ) -> None:
        self.config = config
        self.conn = conn
        self.engagements = engagements
        self.tasks = tasks
        self.scheduler = scheduler
        self.events = events
        self.registry = registry
        self.audit = audit
        self.workspace_provider = workspace_provider
        self.clock = clock
        self.id_gen = id_gen
        self.authorizer = authorizer
        self.home = home

    def open_engagement(self, engagement_id: str) -> Session:
        """Open the engagement-specific SQLite database and return a Session."""
        eng = self.engagements.open(engagement_id)
        db_path = self.workspace_provider.get_db_path(eng.id)

        eng_conn = connect(
            db_path,
            wal=self.config.database.wal,
            busy_timeout_ms=self.config.database.busy_timeout_ms,
        )
        migrate(eng_conn)

        eng_repo = SqliteEngagementRepository(eng_conn)
        scope_repo = SqliteScopeRepository(eng_conn)
        task_repo = SqliteTaskRepository(eng_conn)
        art_repo = SqliteArtifactRepository(eng_conn)
        obs_repo = SqliteObservationRepository(eng_conn)
        audit_sink = SqliteAuditSink(eng_conn)
        audit_logger = AuditLogger(audit_sink, self.clock)

        # Guarantee per-engagement database is seeded with its single engagement and scope
        if eng_repo.get(eng.id) is None:
            eng_repo.save(eng)
            for entry in self.engagements.scope_repo.list_entries(eng.id):
                scope_repo.add_entry(entry)

        session_tasks = TaskService(
            task_repo=task_repo,
            scope_repo=scope_repo,
            registry=self.registry,
            authorizer=self.authorizer,
            audit=audit_logger,
            events=self.events,
            clock=self.clock,
            id_gen=self.id_gen,
        )

        session_scheduler = Scheduler(
            task_repo=task_repo,
            scope_repo=scope_repo,
            eng_repo=eng_repo,
            artifact_repo=art_repo,
            obs_repo=obs_repo,
            registry=self.registry,
            authorizer=self.authorizer,
            audit=audit_logger,
            events=self.events,
            workspace_provider=self.workspace_provider,
            clock=self.clock,
            execution_config=self.config.execution,
        )

        return Session(
            engagement_id=eng.id,
            conn=eng_conn,
            tasks=session_tasks,
            scheduler=session_scheduler,
            audit=audit_logger,
            events=self.events,
            registry=self.registry,
        )

    def init_db(self, db_path: Path) -> None:
        """Initialize and migrate an arbitrary SQLite database path."""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = connect(
            db_path,
            wal=self.config.database.wal,
            busy_timeout_ms=self.config.database.busy_timeout_ms,
        )
        migrate(conn)
        conn.close()

    def close(self) -> None:
        """Release runtime resources."""
        self.scheduler.shutdown()
        with contextlib.suppress(sqlite3.Error):
            self.conn.close()


def build_runtime(
    home: Path | None = None,
    dev: bool = False,
    config: AppConfig | None = None,
    clock: Clock | None = None,
    id_gen: IdGenerator | None = None,
) -> Runtime:
    """Bootstrap and wire the NAYRAASTRA application runtime."""
    effective_home = home or get_home()
    effective_cfg = config or load_config()
    effective_clock = clock or UtcClock()
    effective_id_gen = id_gen or UuidGenerator()

    # Ensure home and root database
    effective_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    db_path = effective_home / effective_cfg.database.filename

    conn = connect(
        db_path,
        wal=effective_cfg.database.wal,
        busy_timeout_ms=effective_cfg.database.busy_timeout_ms,
    )
    migrate(conn)

    # Wire repositories
    eng_repo = SqliteEngagementRepository(conn)
    scope_repo = SqliteScopeRepository(conn)
    task_repo = SqliteTaskRepository(conn)
    art_repo = SqliteArtifactRepository(conn)
    obs_repo = SqliteObservationRepository(conn)
    audit_sink = SqliteAuditSink(conn)

    # Core services
    events = EventBus()
    audit_logger = AuditLogger(audit_sink, effective_clock)
    workspace_provider = DefaultWorkspaceProvider(effective_home)
    authorizer = TaskAuthorizer(effective_clock, effective_cfg.safety)

    engagements = EngagementService(
        repo=eng_repo,
        scope_repo=scope_repo,
        audit_logger=audit_logger,
        workspace_provider=workspace_provider,
        clock=effective_clock,
        home_dir=effective_home,
    )

    registry = AdapterRegistry()
    registry.register(NmapAdapter())

    # Enable fake adapters in development or when explicitly enabled
    is_dev = dev or effective_cfg.adapters.fake_enabled or (os.environ.get("NAYRAASTRA_DEV") == "1")
    if is_dev:
        registry.register(FakeAdapter())
        registry.register(FakeDisruptiveAdapter())

    tasks = TaskService(
        task_repo=task_repo,
        scope_repo=scope_repo,
        registry=registry,
        authorizer=authorizer,
        audit=audit_logger,
        events=events,
        clock=effective_clock,
        id_gen=effective_id_gen,
    )

    scheduler = Scheduler(
        task_repo=task_repo,
        scope_repo=scope_repo,
        eng_repo=eng_repo,
        artifact_repo=art_repo,
        obs_repo=obs_repo,
        registry=registry,
        authorizer=authorizer,
        audit=audit_logger,
        events=events,
        workspace_provider=workspace_provider,
        clock=effective_clock,
        execution_config=effective_cfg.execution,
    )

    return Runtime(
        config=effective_cfg,
        conn=conn,
        engagements=engagements,
        tasks=tasks,
        scheduler=scheduler,
        events=events,
        registry=registry,
        audit=audit_logger,
        workspace_provider=workspace_provider,
        clock=effective_clock,
        id_gen=effective_id_gen,
        authorizer=authorizer,
        home=effective_home,
    )
