"""Main menu screen for top-level SEToolkit-style navigation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from nayraastra.cli.keybindings import (
    KEY_BACK_ZERO,
    KEY_HELP,
    KEY_QUIT,
    MAIN_MENU_KEY_HINTS,
)
from nayraastra.cli.navigation import Exit, Navigation, Push, Screen, Stay
from nayraastra.cli.rendering import (
    render_breadcrumb,
    render_error_panel,
    render_footer_hints,
    safe_text,
)
from nayraastra.cli.screens.engagement import EngagementScreen
from nayraastra.cli.screens.help import HelpScreen
from nayraastra.cli.screens.module_menu import ModuleMenuScreen
from nayraastra.cli.screens.placeholder import PlaceholderScreen
from nayraastra.cli.screens.settings import SettingsScreen
from nayraastra.cli.screens.tasks import TasksScreen
from nayraastra.cli.widgets.menu import MenuItem, render_menu

if TYPE_CHECKING:
    from rich.console import Console

    from nayraastra.cli.input import InputDriver
    from nayraastra.cli.state import SessionState
    from nayraastra.runtime import Runtime


@dataclass(frozen=True)
class MainMenuViewModel:
    """View model for main menu rendering."""

    engagement_name: str
    scope_count: int
    items: tuple[MenuItem, ...]


def build_main_menu_view_model(state: SessionState) -> MainMenuViewModel:
    """Construct view-model for main menu."""
    eng_name = state.engagement.name if state.engagement else "None"
    scope_cnt = len(state.scope_entries) if state.engagement else 0

    items = (
        MenuItem(key="1", label="Reconnaissance"),
        MenuItem(key="2", label="Network Enumeration"),
        MenuItem(key="3", label="Network Analysis"),
        MenuItem(key="4", label="Workflows", badge="planned: Phase 5"),
        MenuItem(key="5", label="Findings & Evidence", badge="planned: Phase 4"),
        MenuItem(key="6", label="Generate Report", badge="planned: Phase 6"),
        MenuItem(key="7", label="Tasks & Audit Log"),
        MenuItem(key="8", label="Engagement"),
        MenuItem(key="9", label="Settings & Environment"),
        MenuItem(key="0", label="Exit"),
    )
    return MainMenuViewModel(
        engagement_name=eng_name,
        scope_count=scope_cnt,
        items=items,
    )


class MainMenuScreen(Screen):
    """Root navigation menu of the NAYRAASTRA framework."""

    title = "Main Menu"
    breadcrumb_title = "NAYRAASTRA"

    def __init__(self) -> None:
        self.notice_message: str | None = None

    def render(self, state: SessionState, console: Console) -> None:
        vm = build_main_menu_view_model(state)

        # Header with engagement context
        header_text = f"NAYRAASTRA  |  Engagement: {safe_text(vm.engagement_name)}  |  Scope: {vm.scope_count}"
        console.print(render_breadcrumb([header_text]))

        if self.notice_message:
            console.print(render_error_panel(self.notice_message, title="Notice"))
            self.notice_message = None

        # Menu options
        console.print(render_menu(vm.items))
        console.print()
        console.print(render_footer_hints(MAIN_MENU_KEY_HINTS))

    async def handle(
        self,
        input_str: str,
        state: SessionState,
        driver: InputDriver,
        runtime: Runtime,
    ) -> Navigation:
        choice = input_str.strip().lower()

        if choice in (KEY_BACK_ZERO, KEY_QUIT):
            # Check if tasks are active before exiting
            if state.running_tasks_count > 0 or state.queued_tasks_count > 0:
                confirmed = await driver.confirm(
                    f"Warning: {state.running_tasks_count} tasks running, {state.queued_tasks_count} queued. Really exit?",
                    default=False,
                )
                if not confirmed:
                    return Stay()
            else:
                confirmed = await driver.confirm("Exit NAYRAASTRA?", default=True)
                if not confirmed:
                    return Stay()
            return Exit()

        if choice == KEY_HELP:
            return Push(HelpScreen())

        if choice in ("1", "2", "3", "7") and (not state.engagement or not state.session):
            self.notice_message = (
                "No active engagement. Open or create an engagement first (Option 8)."
            )
            return Stay()

        if choice == "1":
            return Push(ModuleMenuScreen(module_name="Reconnaissance", category="recon"))
        if choice == "2":
            return Push(ModuleMenuScreen(module_name="Network Enumeration", category="enumeration"))
        if choice == "3":
            return Push(ModuleMenuScreen(module_name="Network Analysis", category="analysis"))
        if choice == "4":
            return Push(
                PlaceholderScreen(
                    title="Workflows",
                    phase_label="Phase 5",
                    description="Automated multi-step orchestration workflows and graph execution.",
                )
            )
        if choice == "5":
            return Push(
                PlaceholderScreen(
                    title="Findings & Evidence",
                    phase_label="Phase 4",
                    description="Vulnerability correlation, evidence vault, and deduplication.",
                )
            )
        if choice == "6":
            return Push(
                PlaceholderScreen(
                    title="Generate Report",
                    phase_label="Phase 6",
                    description="Executive summary, technical findings, and Jinja2 templated reports.",
                )
            )
        if choice == "7":
            return Push(TasksScreen())
        if choice == "8":
            return Push(EngagementScreen())
        if choice == "9":
            return Push(SettingsScreen())

        return Stay()
