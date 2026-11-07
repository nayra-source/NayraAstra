"""Unit tests for UI widgets, view-models, tables, and status bar rendering."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from rich.console import Console

from nayraastra.cli.state import SessionState
from nayraastra.cli.widgets.menu import MenuItem, render_menu
from nayraastra.cli.widgets.progress import LiveProgressView
from nayraastra.cli.widgets.statusbar import build_status_bar_view_model
from nayraastra.cli.widgets.tables import (
    render_observations_table,
    render_scope_table,
    render_tasks_table,
)
from nayraastra.core.domain.models import (
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


@pytest.mark.unit
class TestMenuWidget:
    def test_menu_rendering_and_badges(self) -> None:
        items = (
            MenuItem(key="1", label="Reconnaissance"),
            MenuItem(key="2", label="Port Scan", locked=True, lock_reason="requires ROE opt-in"),
            MenuItem(key="3", label="Workflows", badge="planned: Phase 5"),
            MenuItem(key="0", label="Exit"),
        )
        console = Console(record=True, color_system=None)
        console.print(render_menu(items))
        output = console.export_text()

        assert "1)  Reconnaissance" in output
        assert "2)  Port Scan  [locked: requires ROE opt-in]" in output
        assert "3)  Workflows  (planned: Phase 5)" in output
        assert "0)  Exit" in output

    def test_menu_filter_query(self) -> None:
        items = (
            MenuItem(key="1", label="Host Discovery"),
            MenuItem(key="2", label="Port Scan"),
            MenuItem(key="0", label="Back"),
        )
        console = Console(record=True, color_system=None)
        console.print(render_menu(items, filter_query="port"))
        output = console.export_text()

        assert "Port Scan" in output
        assert "Host Discovery" not in output
        # Back/0 is always preserved
        assert "0)  Back" in output


@pytest.mark.unit
class TestStatusBarViewModel:
    def test_status_bar_no_engagement(self) -> None:
        state = SessionState()
        vm = build_status_bar_view_model(state)
        toolbar = vm.to_toolbar_string()

        assert "No Engagement" in toolbar
        assert "ROE: active-safe" in toolbar
        assert "DRY-RUN: OFF" in toolbar
        assert "Tasks: 0 run / 0 q / 0 fail" in toolbar
        assert "Window: unconstrained" in toolbar
        assert "[DEV]" not in toolbar

    def test_status_bar_with_engagement_and_dev_mode(self) -> None:
        state = SessionState(is_dev=True, dry_run=True)
        now = datetime.now(UTC)
        roe = RulesOfEngagement(
            window_start=now - timedelta(hours=1),
            window_end=now + timedelta(hours=2),
            max_intrusiveness=Intrusiveness.DISRUPTIVE,
            disruptive_enabled=True,
        )
        eng = Engagement(
            id="eng-123",
            name="Alpha Assessment",
            roe=roe,
            created_at=now,
            updated_at=now,
        )
        entry = ScopeEntry(
            id="scope-1",
            engagement_id=eng.id,
            kind=ScopeEntryKind.IP,
            value="192.168.1.1",
            in_scope=True,
            created_at=now,
        )
        state.engagement = eng
        state.scope_entries = [entry]

        vm = build_status_bar_view_model(state)
        toolbar = vm.to_toolbar_string()

        assert "Engagement: Alpha Assessment (Scope: 1)" in toolbar
        assert "ROE: disruptive [DISRUPTIVE ENABLED]" in toolbar
        assert "DRY-RUN: ON" in toolbar
        assert "Window: expires in 1h" in toolbar or "Window: expires in 2h" in toolbar
        assert "[DEV]" in toolbar

    def test_status_bar_expired_window(self) -> None:
        state = SessionState()
        now = datetime.now(UTC)
        roe = RulesOfEngagement(
            window_start=now - timedelta(days=2),
            window_end=now - timedelta(days=1),
        )
        eng = Engagement(
            id="eng-old",
            name="Expired Eng",
            roe=roe,
            created_at=now,
            updated_at=now,
        )
        state.engagement = eng
        assert state.window_status == "EXPIRED"


@pytest.mark.unit
class TestTablesRendering:
    def test_render_scope_table_empty_and_populated(self) -> None:
        console = Console(record=True, color_system=None)
        console.print(render_scope_table([]))
        out_empty = console.export_text()
        assert "No scope entries" in out_empty

        now = datetime.now(UTC)
        entry_in = ScopeEntry(
            id="1",
            engagement_id="e",
            kind=ScopeEntryKind.CIDR,
            value="10.0.0.0/24",
            in_scope=True,
            created_at=now,
        )
        entry_out = ScopeEntry(
            id="2",
            engagement_id="e",
            kind=ScopeEntryKind.IP,
            value="10.0.0.5",
            in_scope=False,
            created_at=now,
        )
        console = Console(record=True, color_system=None)
        console.print(render_scope_table([entry_in, entry_out]))
        out = console.export_text()
        assert "10.0.0.0/24" in out
        assert "IN-SCOPE" in out
        assert "10.0.0.5" in out
        assert "OUT-OF-SCOPE" in out

    def test_render_tasks_table(self) -> None:
        now = datetime.now(UTC)
        t = Task(
            id="task-12345678",
            engagement_id="e",
            module_name="recon",
            adapter_name="fake",
            capability=Capability.PORT_SCAN,
            target=Target(raw="10.10.0.1", normalized="10.10.0.1", kind=TargetKind.IP),
            status=TaskStatus.SUCCEEDED,
            started_at=now,
            finished_at=now + timedelta(seconds=1.5),
            created_at=now,
        )
        console = Console(record=True, color_system=None, width=120)
        console.print(render_tasks_table([t]))
        out = console.export_text()
        assert "task-123" in out
        assert "port_scan" in out
        assert "10.10.0.1" in out
        assert "SUCCEEDED" in out
        assert "1.50s" in out

    def test_render_observations_table(self) -> None:
        now = datetime.now(UTC)
        obs = Observation(
            task_id="t1",
            engagement_id="e",
            observation_key="open_port",
            value={"port": 80, "service": "http", "address": "10.10.0.5"},
            confidence="certain",
            observed_at=now,
        )
        console = Console(record=True, color_system=None)
        console.print(render_observations_table([obs]))
        out = console.export_text()
        assert "open_port" in out
        assert "10.10.0.5" in out
        assert "port=80" in out
        assert "certain" in out


@pytest.mark.unit
class TestLiveProgressView:
    def test_progress_view_sanitization_and_scrollback(self) -> None:
        pv = LiveProgressView(
            task_id="t123", capability="port_scan", target="10.10.0.1", adapter="fake", max_lines=3
        )
        pv.set_running()
        pv.append_output("line 1")
        pv.append_output("line 2 \x1b[31mred\x1b[0m")
        pv.append_output("line 3 [bold red]alert[/bold red]")
        pv.append_output("line 4 overflow")

        assert len(pv.lines) == 3
        # Line 1 dropped due to maxlen=3
        assert "line 1" not in pv.lines
        # ANSI stripped
        assert "\x1b" not in pv.lines[0]
        # Rich markup escaped
        assert r"\[bold red]" in pv.lines[1]
        assert "line 4 overflow" in pv.lines[2]

        rendered = pv.render()
        assert rendered is not None
