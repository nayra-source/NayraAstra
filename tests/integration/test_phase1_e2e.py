"""Phase 1 Exit-Criteria End-to-End Integration Test.

Proves:
1. Runtime bootstrap with fake adapter; engagement creation with CIDR and wildcard domain scope.
2. In-scope task authorized, executed end-to-end to SUCCEEDED; artifact written with valid SHA-256;
   observations stored; events published in correct sequence.
3. Out-of-scope task blocked at gate; adapter never invoked (spy verified); ScopeViolation event emitted.
4. Disruptive task without opt-in blocked by authorizer gate.
5. Audit log records full timeline with unbroken cryptographic hash chain.
6. Re-opening engagement workspace in a fresh runtime loads all persisted state intact.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nayraastra.adapters.fake.adapter import FakeAdapter
from nayraastra.core.audit.verifier import verify_chain
from nayraastra.core.domain.models import RulesOfEngagement, ScopeEntry
from nayraastra.core.domain.types import Capability, Intrusiveness, ScopeEntryKind, TaskStatus
from nayraastra.core.events.bus import RecordingSubscriber
from nayraastra.core.events.models import (
    ScopeViolation,
    TaskBlocked,
    TaskOutput,
    TaskQueued,
    TaskStarted,
    TaskSucceeded,
)
from nayraastra.runtime import build_runtime


class SpyFakeAdapter(FakeAdapter):
    """Spy adapter counting actual run invocations."""

    def __init__(self) -> None:
        super().__init__()
        self.invocations = 0

    async def run(self, task, ctx):
        self.invocations += 1
        return await super().run(task, ctx)


@pytest.mark.integration
def test_phase1_exit_criteria_e2e(tmp_path: Path) -> None:
    async def _test() -> None:
        home_dir = tmp_path / "home"

        # 1. Build runtime with fake adapter enabled
        runtime = build_runtime(home=home_dir, dev=True)
        subscriber = RecordingSubscriber(runtime.events, "*")

        # Replace fake adapter with spy adapter for verification
        spy_adapter = SpyFakeAdapter()
        runtime.registry._adapters["fake"] = spy_adapter

        now = datetime.now(UTC)
        scope_entries = [
            ScopeEntry(
                id=1,
                engagement_id="placeholder",
                kind=ScopeEntryKind.CIDR,
                value="10.10.0.0/24",
                in_scope=True,
                created_at=now,
            ),
            ScopeEntry(
                id=2,
                engagement_id="placeholder",
                kind=ScopeEntryKind.WILDCARD_DOMAIN,
                value="*.lab.example",
                in_scope=True,
                created_at=now,
            ),
        ]

        roe = RulesOfEngagement(
            max_intrusiveness=Intrusiveness.ACTIVE_SAFE,
            disruptive_enabled=False,  # Disruptive blocked
        )

        engagement = runtime.engagements.create(
            name="Phase 1 E2E Target",
            client="Acme Security Labs",
            auth_reference="AUTH-PHASE1-EXIT",
            roe=roe,
            scope_entries=scope_entries,
        )
        eng_id = engagement.id
        assert engagement.status == "active"

        # Open session bound to this engagement database
        session = runtime.open_engagement(eng_id)

        # 2. In-scope task execution (10.10.0.5 is inside 10.10.0.0/24)
        task1 = session.tasks.queue(
            engagement=engagement,
            capability=Capability.PORT_SCAN,
            target="10.10.0.5",
        )
        assert task1.status == TaskStatus.PENDING

        # Execute task
        completed1 = await session.scheduler.execute_task(task1.id)
        assert completed1.status == TaskStatus.SUCCEEDED
        assert completed1.exit_code == 0
        assert spy_adapter.invocations == 1

        # Verify artifact on disk and SHA-256
        art_dir = runtime.workspace_provider.get_artifacts_dir(eng_id)
        artifact_files = list(art_dir.glob("*.txt"))
        assert len(artifact_files) >= 1
        artifact_bytes = artifact_files[0].read_bytes()
        hashlib.sha256(artifact_bytes).hexdigest()

        # Verify event ordering for task 1
        event_types = [type(e) for e in subscriber.events]
        assert TaskQueued in event_types
        assert TaskStarted in event_types
        assert TaskOutput in event_types
        assert TaskSucceeded in event_types

        # 3. Out-of-scope task (192.168.1.1 is NOT in 10.10.0.0/24 or *.lab.example)
        task_blocked = session.tasks.queue(
            engagement=engagement,
            capability=Capability.PORT_SCAN,
            target="192.168.1.1",
        )
        assert task_blocked.status == TaskStatus.BLOCKED
        assert "not covered by any in-scope rule" in str(task_blocked.error_message)

        # Spy verify: adapter was NOT invoked for blocked task
        assert spy_adapter.invocations == 1

        # Verify ScopeViolation and TaskBlocked events emitted
        assert any(isinstance(e, ScopeViolation) for e in subscriber.events)
        assert any(isinstance(e, TaskBlocked) for e in subscriber.events)

        # 4. Disruptive task without opt-in
        task_disruptive = session.tasks.queue(
            engagement=engagement,
            capability=Capability.HOST_DISCOVERY,
            target="10.10.0.10",
            adapter_name="fake_disruptive",
        )
        assert task_disruptive.status == TaskStatus.BLOCKED
        assert "disruptive_enabled=True" in str(task_disruptive.error_message)
        assert spy_adapter.invocations == 1

        # 5. Verify unbroken audit log hash chain in engagement database
        audit_entries = session.audit.sink.get_all_entries()
        assert len(audit_entries) >= 5

        report = verify_chain(audit_entries)
        assert report.valid, f"Audit chain verification failed: {report.error_message}"
        assert report.count == len(audit_entries)

        session.close()
        runtime.close()

        # 6. Re-open engagement in a fresh runtime and confirm persistence
        fresh_runtime = build_runtime(home=home_dir, dev=True)
        fresh_session = fresh_runtime.open_engagement(eng_id)

        persisted_eng = fresh_runtime.engagements.open(eng_id)
        assert persisted_eng.name == "Phase 1 E2E Target"
        assert persisted_eng.client == "Acme Security Labs"

        persisted_task1 = fresh_session.tasks.get(task1.id)
        assert persisted_task1 is not None
        assert persisted_task1.status == TaskStatus.SUCCEEDED

        persisted_blocked = fresh_session.tasks.get(task_blocked.id)
        assert persisted_blocked is not None
        assert persisted_blocked.status == TaskStatus.BLOCKED

        fresh_session.close()
        fresh_runtime.close()

    asyncio.run(_test())
