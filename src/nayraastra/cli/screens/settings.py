"""Settings & Environment screen: effective config, ROE/scope editing, and system diagnostics."""

from __future__ import annotations

import shutil
import sys
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nayraastra.cli.keybindings import GLOBAL_KEY_HINTS, KEY_BACK_ESC, KEY_BACK_ZERO
from nayraastra.cli.navigation import Navigation, Pop, Screen, Stay
from nayraastra.cli.rendering import (
    render_breadcrumb,
    render_error_panel,
    render_footer_hints,
    safe_text,
)
from nayraastra.cli.widgets.menu import MenuItem, render_menu
from nayraastra.cli.widgets.prompts import prompt_field
from nayraastra.cli.widgets.tables import render_scope_table
from nayraastra.core.domain.models import ScopeEntry
from nayraastra.core.domain.types import ScopeEntryKind
from nayraastra.runtime import Runtime, ValidationFailure, normalize_target

if TYPE_CHECKING:
    from rich.console import Console

    from nayraastra.cli.input import InputDriver
    from nayraastra.cli.state import SessionState


class SettingsScreen(Screen):
    """Configuration inspection, environment diagnostics, and live session toggles."""

    title = "Settings & Environment"
    breadcrumb_title = "Settings"

    def __init__(self) -> None:
        self.subview: str = "menu"  # "menu", "config", "scope_manage", "doctor"
        self.notice: str | None = None

    def render(self, state: SessionState, console: Console) -> None:
        console.print(render_breadcrumb(["NAYRAASTRA", "Settings & Environment"]))

        if self.notice:
            console.print(render_error_panel(self.notice, title="Notice"))
            self.notice = None

        if self.subview == "menu":
            self._render_menu(state, console)
        elif self.subview == "config":
            self._render_config(state, console)
        elif self.subview == "scope_manage":
            self._render_scope_manage(state, console)
        elif self.subview == "doctor":
            self._render_doctor(state, console)

        console.print(render_footer_hints(GLOBAL_KEY_HINTS))

    def _render_menu(self, state: SessionState, console: Console) -> None:
        dry_label = f"Toggle dry-run mode (Currently: {'[green]ON[/green]' if state.dry_run else '[dim]OFF[/dim]'})"
        items = (
            MenuItem(key="1", label=dry_label),
            MenuItem(key="2", label="View effective application configuration"),
            MenuItem(
                key="3",
                label="Manage active engagement scope",
                locked=not state.engagement,
                lock_reason="no active engagement",
            ),
            MenuItem(key="4", label="System environment & adapter diagnostics (Doctor)"),
            MenuItem(key="0", label="Back"),
        )
        console.print(render_menu(items))

    def _render_config(self, state: SessionState, console: Console) -> None:
        table = Table(
            title="Effective Application Configuration", show_header=True, header_style="bold cyan"
        )
        table.add_column("Section / Key", width=30, style="cyan")
        table.add_column("Value", style="white")

        if state.config:
            cfg = state.config.execution
            table.add_row("execution.default_timeout_seconds", str(cfg.default_timeout_seconds))
            table.add_row("execution.max_parallel_tasks", str(cfg.max_parallel_tasks))
            table.add_row("execution.rate_limit_per_second", str(cfg.rate_limit_per_second))

        console.print(table)
        console.print("\nPress 0 or Esc to return to settings menu.\n", style="dim")

    def _render_scope_manage(self, state: SessionState, console: Console) -> None:
        if not state.engagement:
            console.print(render_error_panel("No active engagement."))
            return

        is_readonly = state.engagement.status != "active"
        if is_readonly:
            console.print(
                Panel(Text("Engagement is CLOSED (Scope is read-only)", style="bold yellow"))
            )

        console.print(render_scope_table(state.scope_entries))

        if not is_readonly:
            opts = Text()
            opts.append("\nScope Actions: ", style="bold white")
            opts.append("[1] Add Scope Entry   ", style="bold green")
            opts.append("[2] Remove Scope Entry   ", style="bold red")
            opts.append("[0] Back\n", style="bold yellow")
            console.print(opts)

    def _render_doctor(self, state: SessionState, console: Console) -> None:
        table = Table(
            title="System Environment Diagnostics", show_header=True, header_style="bold cyan"
        )
        table.add_column("Component", width=25, style="cyan")
        table.add_column("Status", width=14, justify="center")
        table.add_column("Details", ratio=1, style="dim")

        # Python
        py_ver = sys.version.split()[0]
        py_ok = sys.version_info >= (3, 11)
        table.add_row(
            "Python Runtime",
            "[green]OK[/green]" if py_ok else "[red]FAIL[/red]",
            f"{py_ver} (>=3.11)",
        )

        # Tools
        for tool in ("nmap", "tshark", "bettercap", "hping3"):
            path = shutil.which(tool)
            if path:
                table.add_row(f"Tool: {tool}", "[green]FOUND[/green]", safe_text(path))
            else:
                table.add_row(f"Tool: {tool}", "[dim]MISSING[/dim]", "Not in PATH")

        # Adapters
        if state.session:
            adapters = state.session.registry.list_all()
            adp_str = ", ".join(a.name for a in adapters)
            table.add_row("Registered Adapters", "[green]OK[/green]", safe_text(adp_str))

        console.print(table)
        console.print("\nPress 0 or Esc to return to settings menu.\n", style="dim")

    async def handle(
        self,
        input_str: str,
        state: SessionState,
        driver: InputDriver,
        runtime: Runtime,
    ) -> Navigation:
        ch = input_str.strip().lower()

        if ch in (KEY_BACK_ZERO, KEY_BACK_ESC):
            if self.subview != "menu":
                self.subview = "menu"
                return Stay()
            return Pop()

        if self.subview == "menu":
            if ch == "1":
                state.dry_run = not state.dry_run
                self.notice = f"Dry-run mode is now {'ENABLED' if state.dry_run else 'DISABLED'}."
                return Stay()
            if ch == "2":
                self.subview = "config"
                return Stay()
            if ch == "3":
                if not state.engagement:
                    self.notice = "Open an engagement first."
                    return Stay()
                self.subview = "scope_manage"
                return Stay()
            if ch == "4":
                self.subview = "doctor"
                return Stay()

        elif self.subview == "scope_manage":
            if ch == "1" and state.engagement and state.engagement.status == "active":
                target_str = await prompt_field(driver, "New target address/CIDR")
                if not target_str:
                    return Stay()
                try:
                    norm = normalize_target(target_str)
                except ValidationFailure as exc:
                    self.notice = f"Invalid target: {exc}"
                    return Stay()

                in_scope = await driver.confirm("Is this in-scope?", default=True)
                note = await prompt_field(driver, "Optional note", required=False) or ""

                entry = ScopeEntry(
                    id=runtime.id_gen.generate(),
                    engagement_id=state.engagement.id,
                    kind=ScopeEntryKind(norm.kind.value),
                    value=norm.raw,
                    in_scope=in_scope,
                    note=note,
                    created_at=runtime.clock.now(),
                )
                saved = runtime.engagements.add_scope_entry(state.engagement.id, entry)
                state.scope_entries.append(saved)
                self.notice = f"Added target '{saved.value}' to scope."
                return Stay()

            if ch == "2" and state.engagement and state.engagement.status == "active":
                if not state.scope_entries:
                    self.notice = "Scope is empty."
                    return Stay()
                val = await prompt_field(driver, "Target value to remove")
                if not val:
                    return Stay()
                to_remove = [e for e in state.scope_entries if e.value == val]
                if not to_remove:
                    self.notice = f"Target '{val}' not found in scope."
                    return Stay()
                for e in to_remove:
                    if e.id is not None:
                        runtime.engagements.remove_scope_entry(state.engagement.id, e.id)
                    state.scope_entries.remove(e)
                self.notice = f"Removed '{val}' from scope."
                return Stay()

        return Stay()
