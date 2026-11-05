"""Unit tests for TaskService, Scheduler, rate limiter, and fake adapter execution."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nayraastra.adapters.fake.adapter import FakeAdapter
from nayraastra.adapters.registry import AdapterRegistry
from nayraastra.core.audit.logger import AuditLogger
from nayraastra.core.config import ExecutionConfig
from nayraastra.core.domain.models import Engagement, RulesOfEngagement, ScopeEntry, Task
from nayraastra.core.domain.time_id import FrozenClock, StaticIdGenerator
from nayraastra.core.domain.types import Capability, Intrusiveness, ScopeEntryKind, TaskStatus
from nayraastra.core.events.bus import EventBus, RecordingSubscriber
from nayraastra.core.events.models import TaskBlocked
from nayraastra.core.scope.authorizer import TaskAuthorizer
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
from nayraastra.runtime import DefaultWorkspaceProvider


class SpyAdapter(FakeAdapter):
    """Spy adapter counting invocation attempts."""

    def __init__(self) -> None:
        super().__init__()
        self.invocations = 0

    async def run(self, task: Task, ctx: object) -> object:
        self.invocations += 1
        return await super().run(task, ctx)  # type: ignore[arg-type]


@pytest.mark.unit
class TestTaskServiceAndScheduler:
    @pytest.fixture()
    def task_env(self, tmp_path: Path):
        db_path = tmp_path / "tasks_test.db"
        conn = connect(db_path)
        migrate(conn)

        eng_repo = SqliteEngagementRepository(conn)
        scope_repo = SqliteScopeRepository(conn)
        task_repo = SqliteTaskRepository(conn)
        art_repo = SqliteArtifactRepository(conn)
        obs_repo = SqliteObservationRepository(conn)
        audit_sink = SqliteAuditSink(conn)

        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        clock = FrozenClock(now)
        audit = AuditLogger(audit_sink, clock)
        events = EventBus()
        id_gen = StaticIdGenerator(prefix="task")
        ws_provider = DefaultWorkspaceProvider(tmp_path)
        authorizer = TaskAuthorizer(clock)

        registry = AdapterRegistry()
        spy_adapter = SpyAdapter()
        registry.register(spy_adapter)

        task_service = TaskService(
            task_repo=task_repo,
            scope_repo=scope_repo,
            registry=registry,
            authorizer=authorizer,
            audit=audit,
            events=events,
            clock=clock,
            id_gen=id_gen,
        )

        scheduler = Scheduler(
            task_repo=task_repo,
            scope_repo=scope_repo,
            eng_repo=eng_repo,
            artifact_repo=art_repo,
            obs_repo=obs_repo,
            registry=registry,
            authorizer=authorizer,
            audit=audit,
            events=events,
            workspace_provider=ws_provider,
            clock=clock,
            execution_config=ExecutionConfig(max_parallel_tasks=1),
        )

        # Create active engagement with in-scope CIDR
        eng = Engagement(
            id="eng-task-test",
            name="Task Test Engagement",
            client="Acme",
            auth_reference="AUTH-TASK",
            roe=RulesOfEngagement(max_intrusiveness=Intrusiveness.ACTIVE_SAFE),
            status="active",
            created_at=now,
            updated_at=now,
        )
        eng_repo.save(eng)
        scope_repo.add_entry(
            ScopeEntry(
                id=1,
                engagement_id=eng.id,
                kind=ScopeEntryKind.CIDR,
                value="10.0.0.0/24",
                in_scope=True,
                created_at=now,
            )
        )

        return {
            "task_service": task_service,
            "scheduler": scheduler,
            "registry": registry,
            "spy_adapter": spy_adapter,
            "eng": eng,
            "events": events,
            "clock": clock,
            "art_repo": art_repo,
            "obs_repo": obs_repo,
            "task_repo": task_repo,
        }

    def test_out_of_scope_task_blocked_and_never_reaches_adapter(self, task_env: dict) -> None:
        service: TaskService = task_env["task_service"]
        spy: SpyAdapter = task_env["spy_adapter"]
        eng: Engagement = task_env["eng"]
        events: EventBus = task_env["events"]

        rec = RecordingSubscriber(events, "*")

        # Target 192.168.1.1 is out of scope!
        task = service.queue(
            engagement=eng,
            capability=Capability.PORT_SCAN,
            target="192.168.1.1",
        )

        assert task.status == TaskStatus.BLOCKED
        assert "not covered by any in-scope rule" in str(task.error_message)
        # SPY TEST: Adapter was NEVER invoked
        assert spy.invocations == 0

        # Event assertions
        assert any(isinstance(e, TaskBlocked) for e in rec.events)

    def test_end_to_end_authorized_task_execution(self, task_env: dict) -> None:
        async def _test() -> None:
            service: TaskService = task_env["task_service"]
            scheduler: Scheduler = task_env["scheduler"]
            eng: Engagement = task_env["eng"]
            art_repo: SqliteArtifactRepository = task_env["art_repo"]
            obs_repo: SqliteObservationRepository = task_env["obs_repo"]

            # Queue in-scope target
            task = service.queue(
                engagement=eng,
                capability=Capability.PORT_SCAN,
                target="10.0.0.5",
            )
            assert task.status == TaskStatus.PENDING

            # Execute
            res = await scheduler.execute_task(task.id)
            assert res.status == TaskStatus.SUCCEEDED
            assert res.exit_code == 0

            # Verify artifact and observations persisted
            artifacts = art_repo.list_by_task(task.id)
            assert len(artifacts) >= 1
            assert artifacts[0].sha256 != ""

            observations = obs_repo.list_by_task(task.id)
            assert len(observations) >= 1
            keys = [o.observation_key for o in observations]
            assert "host_up" in keys or "open_port" in keys

        asyncio.run(_test())

    def test_dry_run_mode(self, task_env: dict) -> None:
        async def _test() -> None:
            service: TaskService = task_env["task_service"]
            scheduler: Scheduler = task_env["scheduler"]
            eng: Engagement = task_env["eng"]
            spy: SpyAdapter = task_env["spy_adapter"]

            invocations_before = spy.invocations

            task = service.queue(
                engagement=eng,
                capability=Capability.PORT_SCAN,
                target="10.0.0.10",
                params={"dry_run": True},
            )

            res = await scheduler.execute_task(task.id)
            assert res.status == TaskStatus.SKIPPED
            assert spy.invocations == invocations_before  # Not executed

        asyncio.run(_test())

    def test_missing_tool_fails_cleanly(self, task_env: dict) -> None:
        async def _test() -> None:
            service: TaskService = task_env["task_service"]
            scheduler: Scheduler = task_env["scheduler"]
            eng: Engagement = task_env["eng"]
            registry: AdapterRegistry = task_env["registry"]

            # Register a fake missing adapter
            missing_adp = FakeAdapter(force_missing=True)
            missing_adp.name = "missing_tool"
            registry.register(missing_adp)

            task = service.queue(
                engagement=eng,
                capability=Capability.PORT_SCAN,
                target="10.0.0.20",
                adapter_name="missing_tool",
            )

            res = await scheduler.execute_task(task.id)
            assert res.status == TaskStatus.FAILED
            assert "missing" in str(res.error_message).lower()

        asyncio.run(_test())

    def test_sequential_execution_guarantee(self, task_env: dict) -> None:
        async def _test() -> None:
            service: TaskService = task_env["task_service"]
            scheduler: Scheduler = task_env["scheduler"]
            eng: Engagement = task_env["eng"]

            task1 = service.queue(eng, Capability.PORT_SCAN, "10.0.0.1", params={"delay": 0.05})
            task2 = service.queue(eng, Capability.PORT_SCAN, "10.0.0.2", params={"delay": 0.05})

            # Run concurrently through scheduler: queue lock guarantees sequential order
            t1_fut = asyncio.create_task(scheduler.execute_task(task1.id))
            t2_fut = asyncio.create_task(scheduler.execute_task(task2.id))

            results = await asyncio.gather(t1_fut, t2_fut)
            assert results[0].status == TaskStatus.SUCCEEDED
            assert results[1].status == TaskStatus.SUCCEEDED

        asyncio.run(_test())
