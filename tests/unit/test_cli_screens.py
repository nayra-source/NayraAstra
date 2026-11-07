"""Unit tests for individual screens: MainMenu, EngagementWizard, ModuleMenu, Tasks, and Audit."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from rich.console import Console

from nayraastra.cli.input import ScriptedInputDriver
from nayraastra.cli.keybindings import KEY_BACK_ZERO
from nayraastra.cli.navigation import Pop, Stay
from nayraastra.cli.screens.audit import AuditScreen
from nayraastra.cli.screens.engagement_wizard import EngagementWizardScreen, parse_time_shortcut
from nayraastra.cli.screens.module_menu import ModuleMenuScreen
from nayraastra.cli.state import SessionState
from nayraastra.core.domain.models import RulesOfEngagement, ScopeEntry
from nayraastra.core.domain.types import (
    Intrusiveness,
    ScopeEntryKind,
)
from nayraastra.runtime import build_runtime


@pytest.mark.unit
class TestTimeShortcuts:
    def test_parse_time_shortcut(self) -> None:
        ref = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)
        assert parse_time_shortcut("now", ref_time=ref) == ref
        assert parse_time_shortcut("+1d", ref_time=ref) == ref + timedelta(days=1)
        assert parse_time_shortcut("+24h", ref_time=ref) == ref + timedelta(hours=24)
        assert parse_time_shortcut("", ref_time=ref) is None

        iso_parsed = parse_time_shortcut("2026-11-10T15:30:00")
        assert iso_parsed is not None
        assert iso_parsed.year == 2026

        with pytest.raises(ValueError, match="Invalid date/time"):
            parse_time_shortcut("invalid-date-string")


@pytest.mark.unit
class TestEngagementWizard:
    def test_wizard_cancel_at_first_prompt(self, tmp_path: Path) -> None:
        async def _test() -> None:
            rt = build_runtime(home=tmp_path, dev=True)
            try:
                wizard = EngagementWizardScreen()
                state = SessionState()
                driver = ScriptedInputDriver([KEY_BACK_ZERO])

                action = await wizard.handle(KEY_BACK_ZERO, state, driver, rt)
                assert isinstance(action, Pop)
            finally:
                rt.close()

        asyncio.run(_test())

    def test_wizard_happy_path(self, tmp_path: Path) -> None:
        async def _test() -> None:
            rt = build_runtime(home=tmp_path, dev=True)
            try:
                wizard = EngagementWizardScreen()
                state = SessionState()

                # Step 1: Info inputs (Name, Client, AuthRef, Start, End, Intrusiveness)
                driver = ScriptedInputDriver(
                    [
                        "Audit Corp",  # Name
                        "ACME Inc",  # Client
                        "AUTH-2026-001",  # Auth Ref
                        "now",  # Start
                        "+7d",  # End
                        "2",  # Max intrusiveness (active-safe)
                    ]
                )
                action1 = await wizard.handle("1", state, driver, rt)
                assert isinstance(action1, Stay)
                assert wizard.step == 2

                # Step 2: Add scope entries
                driver.feed("10.10.0.0/24", "y", "Internal subnet")
                action2 = await wizard.handle("1", state, driver, rt)
                assert isinstance(action2, Stay)
                assert len(wizard.data.scope_entries) == 1

                # Finish scope: choice '3'
                action3 = await wizard.handle("3", state, driver, rt)
                assert isinstance(action3, Stay)
                assert wizard.step == 3

                # Step 3: Review and confirm
                driver.feed("y")
                action4 = await wizard.handle("1", state, driver, rt)
                assert isinstance(action4, Pop)

                # Assert session was created and bound to state
                assert state.engagement is not None
                assert state.engagement.name == "Audit Corp"
                assert state.session is not None
                assert len(state.scope_entries) == 1
            finally:
                rt.close()

        asyncio.run(_test())

    def test_wizard_disruptive_confirmation_rejected(self, tmp_path: Path) -> None:
        async def _test() -> None:
            rt = build_runtime(home=tmp_path, dev=True)
            try:
                wizard = EngagementWizardScreen()
                state = SessionState()

                driver = ScriptedInputDriver(
                    [
                        "Danger Mission",  # Name
                        "Target Co",  # Client
                        "AUTH-RED",  # Auth Ref
                        "",  # Start (immediate)
                        "",  # End (indefinite)
                        "4",  # Disruptive
                        "wrong phrase",  # Mismatched confirmation phrase
                    ]
                )
                await wizard.handle("1", state, driver, rt)
                assert wizard.data.max_intrusiveness == Intrusiveness.ACTIVE_SAFE
                assert wizard.data.disruptive_enabled is False
            finally:
                rt.close()

        asyncio.run(_test())


@pytest.mark.unit
class TestModuleMenuScreen:
    def test_module_menu_locking_rules(self, tmp_path: Path) -> None:
        rt = build_runtime(home=tmp_path, dev=True)
        try:
            screen = ModuleMenuScreen("Network Enumeration", "enumeration")
            state = SessionState()

            # No engagement open -> locked
            console = Console(record=True, color_system=None)
            screen.render(state, console)
            out = console.export_text()
            assert "locked: no engagement open" in out

            # Open engagement with ACTIVE_SAFE ceiling
            eng = rt.engagements.create(
                name="Safe Eng",
                client="ACME",
                auth_reference="AUTH-1",
                roe=RulesOfEngagement(max_intrusiveness=Intrusiveness.ACTIVE_SAFE),
                scope_entries=[
                    ScopeEntry(
                        id="s1",
                        engagement_id="",
                        kind=ScopeEntryKind.IP,
                        value="10.0.0.1",
                        in_scope=True,
                        created_at=rt.clock.now(),
                    )
                ],
            )
            session = rt.open_engagement(eng.id)
            state.set_session(session, eng)

            console2 = Console(record=True, color_system=None)
            screen.render(state, console2)
            out2 = console2.export_text()
            # Port Scan and Service Detect should be available
            assert "1)  TCP / UDP Port Scan" in out2
            assert "2)  Service Version Detection" in out2
        finally:
            rt.close()


@pytest.mark.unit
class TestAuditTamperingDetection:
    def test_audit_screen_detects_hash_tampering(self, tmp_path: Path) -> None:
        async def _test() -> None:
            rt = build_runtime(home=tmp_path, dev=True)
            try:
                # Create engagement and log events
                eng = rt.engagements.create(
                    name="Audit Test",
                    client="Client",
                    auth_reference="AUTH-1",
                    scope_entries=[
                        ScopeEntry(
                            id="s1",
                            engagement_id="",
                            kind=ScopeEntryKind.IP,
                            value="10.0.0.1",
                            in_scope=True,
                            created_at=rt.clock.now(),
                        )
                    ],
                )
                session = rt.open_engagement(eng.id)
                session.audit.log("engagement.opened", "engagement", eng.id, {"name": eng.name})
                state = SessionState()
                state.set_session(session, eng)

                # Initial chain is valid
                screen = AuditScreen()
                console = Console(record=True, color_system=None)
                screen.render(state, console)
                assert "✓ HASH-CHAIN VALID" in console.export_text()

                # Directly tamper with SQLite entry_hash
                db_path = rt.workspace_provider.get_db_path(eng.id)
                conn = sqlite3.connect(str(db_path))
                conn.execute("PRAGMA foreign_keys = OFF;")
                conn.execute("DROP TRIGGER IF EXISTS audit_log_no_update;")
                conn.execute(
                    "UPDATE audit_log SET entry_hash = 'tampered_hash_value' WHERE id = 1;"
                )
                conn.commit()
                conn.close()

                console_tampered = Console(record=True, color_system=None)
                screen.render(state, console_tampered)
                out_tampered = console_tampered.export_text()
                assert "✗ HASH-CHAIN BROKEN" in out_tampered
            finally:
                rt.close()

        asyncio.run(_test())
