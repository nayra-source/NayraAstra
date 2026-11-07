"""Unit tests for the RunFlowScreen: target selection, plan preview, live progress, and results."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from rich.console import Console

from nayraastra.adapters.fake.adapter import FakeAdapter
from nayraastra.cli.input import ScriptedInputDriver
from nayraastra.cli.navigation import Stay
from nayraastra.cli.screens.run_flow import RunFlowScreen
from nayraastra.cli.state import SessionState
from nayraastra.core.domain.models import ScopeEntry
from nayraastra.core.domain.types import Capability, ScopeEntryKind, TaskStatus
from nayraastra.runtime import build_runtime


@pytest.mark.unit
class TestRunFlow:
    def test_run_flow_successful_task(self, tmp_path: Path) -> None:
        async def _test() -> None:
            rt = build_runtime(home=tmp_path, dev=True)
            try:
                eng = rt.engagements.create(
                    name="Scan Corp",
                    client="ACME",
                    auth_reference="AUTH-1",
                    scope_entries=[
                        ScopeEntry(
                            id="s1",
                            engagement_id="",
                            kind=ScopeEntryKind.CIDR,
                            value="10.10.0.0/24",
                            in_scope=True,
                            created_at=rt.clock.now(),
                        )
                    ],
                )
                session = rt.open_engagement(eng.id)
                state = SessionState()
                state.set_session(session, eng, rt.engagements.scope_repo.list_entries(eng.id))

                fake_adapter = FakeAdapter()
                flow = RunFlowScreen("Recon", Capability.PORT_SCAN, "Port Scan", fake_adapter)

                # Step 1: Select target "10.10.0.5"
                driver = ScriptedInputDriver()
                action1 = await flow.handle("10.10.0.5", state, driver, rt)
                assert isinstance(action1, Stay)
                assert flow.step == 3  # Moved to plan preview

                # Step 3: Confirm execution
                action2 = await flow.handle("y", state, driver, rt)
                assert isinstance(action2, Stay)
                assert flow.step == 5  # Result view

                assert flow.executed_task is not None
                assert flow.executed_task.status == TaskStatus.SUCCEEDED
                assert flow.executed_task.exit_code == 0

                # Render result view
                console = Console(record=True, color_system=None)
                flow.render(state, console)
                output = console.export_text()
                assert "Task SUCCEEDED" in output
                assert "open_port" in output
            finally:
                rt.close()

        asyncio.run(_test())

    def test_run_flow_blocked_out_of_scope_target(self, tmp_path: Path) -> None:
        async def _test() -> None:
            rt = build_runtime(home=tmp_path, dev=True)
            try:
                eng = rt.engagements.create(
                    name="Scope Guard Test",
                    client="ACME",
                    auth_reference="AUTH-2",
                    scope_entries=[
                        ScopeEntry(
                            id="s1",
                            engagement_id="",
                            kind=ScopeEntryKind.CIDR,
                            value="10.10.0.0/24",
                            in_scope=True,
                            created_at=rt.clock.now(),
                        ),
                        ScopeEntry(
                            id="s2",
                            engagement_id="",
                            kind=ScopeEntryKind.IP,
                            value="10.10.0.99",
                            in_scope=False,
                            created_at=rt.clock.now(),
                        ),
                    ],
                )
                session = rt.open_engagement(eng.id)
                state = SessionState()
                state.set_session(session, eng, rt.engagements.scope_repo.list_entries(eng.id))

                fake_adapter = FakeAdapter()
                flow = RunFlowScreen("Recon", Capability.PORT_SCAN, "Port Scan", fake_adapter)

                # Enter out-of-scope target
                driver = ScriptedInputDriver()
                await flow.handle("10.10.0.99", state, driver, rt)
                assert flow.step == 3

                # Confirm launch
                await flow.handle("y", state, driver, rt)
                assert flow.step == 5

                # Assert task is BLOCKED and adapter was never invoked
                assert flow.executed_task is not None
                assert flow.executed_task.status == TaskStatus.BLOCKED
                assert "matches out-of-scope rule" in str(flow.executed_task.error_message).lower()

                console = Console(record=True, color_system=None)
                flow.render(state, console)
                output = console.export_text()
                assert "Task BLOCKED by Scope Guard" in output
            finally:
                rt.close()

        asyncio.run(_test())

    def test_run_flow_dry_run_mode(self, tmp_path: Path) -> None:
        async def _test() -> None:
            rt = build_runtime(home=tmp_path, dev=True)
            try:
                eng = rt.engagements.create(
                    name="DryRun Test",
                    client="ACME",
                    auth_reference="AUTH-3",
                    scope_entries=[
                        ScopeEntry(
                            id="s1",
                            engagement_id="",
                            kind=ScopeEntryKind.IP,
                            value="192.168.1.1",
                            in_scope=True,
                            created_at=rt.clock.now(),
                        )
                    ],
                )
                session = rt.open_engagement(eng.id)
                state = SessionState(dry_run=True)
                state.set_session(session, eng, rt.engagements.scope_repo.list_entries(eng.id))

                fake_adapter = FakeAdapter()
                flow = RunFlowScreen(
                    "Recon", Capability.HOST_DISCOVERY, "Host Discovery", fake_adapter
                )

                driver = ScriptedInputDriver()
                await flow.handle("192.168.1.1", state, driver, rt)
                await flow.handle("y", state, driver, rt)

                assert flow.executed_task is not None
                assert flow.executed_task.status == TaskStatus.SKIPPED

                console = Console(record=True, color_system=None)
                flow.render(state, console)
                assert "Task SKIPPED (Dry-Run Mode" in console.export_text()
            finally:
                rt.close()

        asyncio.run(_test())
