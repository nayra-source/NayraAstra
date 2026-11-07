"""Phase 2 exit-criteria end-to-end integration test.

Executes a fully scripted, keyboard-only session exercising the entire
SEToolkit-style shell navigation, engagement lifecycle, scope enforcement,
task execution, tamper-evident audit trail, and workspace resumption.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from rich.console import Console

from nayraastra.cli.app import App
from nayraastra.cli.input import ScriptedInputDriver
from nayraastra.core.domain.types import TaskStatus
from nayraastra.runtime import build_runtime, verify_chain


@pytest.mark.integration
class TestPhase2CliE2E:
    def test_complete_keyboard_driven_session(self, tmp_path: Path) -> None:
        async def _test() -> None:
            home_dir = tmp_path / "nayraastra_home"
            home_dir.mkdir(parents=True, exist_ok=True)

            console = Console(record=True, color_system=None)

            # -------------------------------------------------------------------
            # SESSION 1: Create engagement, execute tasks, verify audit, exit
            # -------------------------------------------------------------------
            rt1 = build_runtime(home=home_dir, dev=True)
            driver1 = ScriptedInputDriver()
            app1 = App(runtime=rt1, driver=driver1, console=console, is_dev=True)

            # 1. Main Menu -> Option 8 (Engagement)
            driver1.feed("8")

            # Engagement Menu -> Option 1 (Create new engagement wizard)
            driver1.feed("1")

            # Wizard Step 1: Engagement Info
            driver1.feed(
                "E2E Penetration Test",  # Name
                "Global Defense Corp",  # Client
                "AUTH-2026-E2E-001",  # Auth Reference
                "now",  # Window Start
                "+7d",  # Window End
                "2",  # Max Intrusiveness: active-safe
            )

            # Wizard Step 2: Add Scope Entries
            # Entry 1 (In-Scope subnet: 10.10.0.0/24)
            driver1.feed("1", "10.10.0.0/24", "y", "Allowed target range")
            # Entry 2 (Out-of-Scope exclusion: 10.10.0.99)
            driver1.feed("1", "10.10.0.99", "n", "Excluded DC")
            # Finish scope
            driver1.feed("3")

            # Wizard Step 3: Final Review and Confirm
            driver1.feed("y")

            # Engagement created! Back to Main Menu: press '0' on Engagement screen
            driver1.feed("0")

            # 2. Network Enumeration (Option 2) -> Port Scan (Option 1)
            driver1.feed("2", "1")
            # Target input: 10.10.0.5 (in-scope)
            driver1.feed("10.10.0.5")
            # Plan preview confirm: 'y'
            driver1.feed("y")
            # Result view -> press '0' to return to Enumeration menu -> '0' to Main Menu
            driver1.feed("0", "0")

            # 3. Repeat for Out-of-Scope target: 10.10.0.99
            driver1.feed("2", "1")
            # Target input: 10.10.0.99
            driver1.feed("10.10.0.99")
            # Plan preview confirm: 'y'
            driver1.feed("y")
            # Result view (BLOCKED) -> '0' to Enumeration menu -> '0' to Main Menu
            driver1.feed("0", "0")

            # 4. Tasks & Audit Log (Option 7) -> Audit Trail ('a')
            driver1.feed("7", "a")
            # In Audit Screen -> '0' back to Tasks -> '0' back to Main Menu
            driver1.feed("0", "0")

            # 5. Main Menu -> Exit ('0' then confirm 'y')
            driver1.feed("0", "y")

            # Run Session 1
            exit_code1 = await app1.run_async()
            assert exit_code1 == 0

            # Assertions on Session 1 results
            assert app1.state.engagement is not None
            eng_id = app1.state.engagement.id

            # Verify tasks in SQLite
            tasks = app1.state.tasks_cache
            assert len(tasks) == 2

            task_succ = next(t for t in tasks if t.target.raw == "10.10.0.5")
            assert task_succ.status == TaskStatus.SUCCEEDED
            assert task_succ.exit_code == 0

            task_blocked = next(t for t in tasks if t.target.raw == "10.10.0.99")
            assert task_blocked.status == TaskStatus.BLOCKED
            assert "out-of-scope rule" in str(task_blocked.error_message).lower()

            # -------------------------------------------------------------------
            # SESSION 2: Restart app, Load engagement, verify persistence
            # -------------------------------------------------------------------
            rt2 = build_runtime(home=home_dir, dev=True)
            driver2 = ScriptedInputDriver()
            app2 = App(runtime=rt2, driver=driver2, console=console, is_dev=True)

            # Main Menu -> Option 8 (Engagement)
            driver2.feed("8")
            # Engagement Menu -> Option 2 (Load existing engagement)
            driver2.feed("2")
            # Select first engagement in list ('1')
            driver2.feed("1")
            # Back to Main Menu ('0')
            driver2.feed("0")
            # Exit ('0' then 'y')
            driver2.feed("0", "y")

            exit_code2 = await app2.run_async()
            assert exit_code2 == 0

            # Verify engagement loaded successfully
            assert app2.state.engagement is not None
            assert app2.state.engagement.id == eng_id
            assert app2.state.engagement.name == "E2E Penetration Test"

            # Verify persisted tasks and audit chain
            assert len(app2.state.tasks_cache) == 2
            entries = app2.state.session.audit.sink.get_all_entries() if app2.state.session else []
            assert len(entries) >= 5

            # Verify cryptographic integrity of the persisted chain
            report = verify_chain(entries)
            assert report.valid is True
            assert report.count == len(entries)

        asyncio.run(_test())
