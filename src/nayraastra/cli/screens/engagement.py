"""Engagement management screens: menu, list/load, details, and session closing."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nayraastra.cli.keybindings import (
    GLOBAL_KEY_HINTS,
    KEY_BACK_ESC,
    KEY_BACK_ZERO,
    KEY_SEARCH,
)
from nayraastra.cli.navigation import Navigation, Pop, Push, Screen, Stay
from nayraastra.cli.rendering import (
    render_breadcrumb,
    render_error_panel,
    render_footer_hints,
    safe_text,
)
from nayraastra.cli.screens.engagement_wizard import EngagementWizardScreen
from nayraastra.cli.widgets.menu import MenuItem, render_menu
from nayraastra.cli.widgets.prompts import prompt_field
from nayraastra.cli.widgets.tables import render_engagements_table, render_scope_table
from nayraastra.core.domain.models import Engagement

if TYPE_CHECKING:
    from rich.console import Console

    from nayraastra.cli.input import InputDriver
    from nayraastra.cli.state import SessionState
    from nayraastra.runtime import Runtime


class EngagementScreen(Screen):
    """Engagement management home menu."""

    title = "Engagement Management"
    breadcrumb_title = "Engagement"

    def __init__(self) -> None:
        self.notice: str | None = None

    def render(self, state: SessionState, console: Console) -> None:
        console.print(render_breadcrumb(["NAYRAASTRA", "Engagement Management"]))

        if self.notice:
            console.print(render_error_panel(self.notice, title="Notice"))
            self.notice = None

        has_active = state.engagement is not None
        active_label = (
            f"Active: {safe_text(state.engagement.name)}"
            if state.engagement
            else "No active engagement"
        )

        items = (
            MenuItem(key="1", label="Create new engagement"),
            MenuItem(key="2", label="Load existing engagement"),
            MenuItem(
                key="3",
                label="View active engagement details",
                locked=not has_active,
                lock_reason="no active engagement",
            ),
            MenuItem(
                key="4",
                label="Close active engagement",
                locked=not has_active,
                lock_reason="no active engagement",
            ),
            MenuItem(key="0", label="Back"),
        )

        console.print(
            Panel(Text(active_label, style="bold cyan"), title="Current Context", padding=(0, 1))
        )
        console.print(render_menu(items))
        console.print()
        console.print(render_footer_hints(GLOBAL_KEY_HINTS))

    async def handle(
        self,
        input_str: str,
        state: SessionState,
        driver: InputDriver,
        runtime: Runtime,
    ) -> Navigation:
        ch = input_str.strip().lower()

        if ch in (KEY_BACK_ZERO, KEY_BACK_ESC):
            return Pop()

        if ch == "1":
            return Push(EngagementWizardScreen())

        if ch == "2":
            eng_list = runtime.engagements.list()
            return Push(LoadEngagementScreen(eng_list))

        if ch == "3":
            if not state.engagement:
                self.notice = "No active engagement is open."
                return Stay()
            return Push(EngagementDetailsScreen())

        if ch == "4":
            if not state.engagement:
                self.notice = "No active engagement is open."
                return Stay()
            state.close_session()
            self.notice = "Engagement session closed."
            return Stay()

        return Stay()


class LoadEngagementScreen(Screen):
    """Lists available engagements and handles loading workspaces."""

    title = "Load Engagement"
    breadcrumb_title = "Load"

    def __init__(self, engagements: Sequence[Engagement] | None = None) -> None:
        self.engagements: list[Engagement] = list(engagements or [])
        self.search_query: str = ""
        self.notice: str | None = None

    def render(self, state: SessionState, console: Console) -> None:
        console.print(render_breadcrumb(["NAYRAASTRA", "Engagement", "Load Existing"]))

        if self.notice:
            console.print(render_error_panel(self.notice, title="Notice"))
            self.notice = None

        console.print(render_engagements_table(self.engagements, filter_query=self.search_query))
        console.print()
        console.print(render_footer_hints(GLOBAL_KEY_HINTS))

    async def handle(
        self,
        input_str: str,
        state: SessionState,
        driver: InputDriver,
        runtime: Runtime,
    ) -> Navigation:
        ch = input_str.strip()

        if ch in (KEY_BACK_ZERO, KEY_BACK_ESC):
            return Pop()

        if ch == KEY_SEARCH:
            q = await prompt_field(driver, "Filter engagements", required=False)
            self.search_query = q or ""
            return Stay()

        try:
            self.engagements = runtime.engagements.list()
        except Exception as exc:
            self.notice = f"Failed to list engagements: {exc}"
            return Stay()

        # Handle numeric selection
        if ch.isdigit():
            idx = int(ch) - 1
            if 0 <= idx < len(self.engagements):
                target_eng = self.engagements[idx]
                try:
                    session = runtime.open_engagement(target_eng.id)
                    entries = list(runtime.engagements.scope_repo.list_entries(target_eng.id))
                    state.set_session(session, target_eng, entries)
                    return Pop()
                except Exception as exc:
                    self.notice = f"Failed to load engagement workspace: {exc}"
                    return Stay()

        return Stay()


class EngagementDetailsScreen(Screen):
    """Displays detailed metadata, ROE, and scope rules of the active engagement."""

    title = "Engagement Details"
    breadcrumb_title = "Details"

    def render(self, state: SessionState, console: Console) -> None:
        console.print(render_breadcrumb(["NAYRAASTRA", "Engagement", "Active Details"]))

        if not state.engagement:
            console.print(render_error_panel("No active engagement."))
            console.print(render_footer_hints(GLOBAL_KEY_HINTS))
            return

        eng = state.engagement
        table = Table(
            title="Engagement Specifications", show_header=False, box=None, padding=(0, 1)
        )
        table.add_column("Property", style="bold cyan", width=22)
        table.add_column("Value", style="white")

        table.add_row("ID:", safe_text(eng.id))
        table.add_row("Name:", safe_text(eng.name))
        table.add_row("Client:", safe_text(eng.client or "-"))
        table.add_row("Auth Reference:", safe_text(eng.auth_reference))
        table.add_row("Status:", safe_text(eng.status.upper()))
        table.add_row("Max Intrusiveness:", safe_text(eng.roe.max_intrusiveness.value))
        table.add_row("Disruptive Opt-In:", "ENABLED" if eng.roe.disruptive_enabled else "DISABLED")
        table.add_row("Created At:", eng.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"))

        console.print(Panel(table, title="[bold cyan]Metadata[/bold cyan]", padding=(0, 1)))
        console.print(render_scope_table(state.scope_entries))
        console.print(render_footer_hints(GLOBAL_KEY_HINTS))

    async def handle(
        self,
        input_str: str,
        state: SessionState,
        driver: InputDriver,
        runtime: Runtime,
    ) -> Navigation:
        if input_str in (KEY_BACK_ZERO, KEY_BACK_ESC):
            return Pop()
        return Stay()
