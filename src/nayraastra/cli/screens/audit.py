"""Paged audit log viewer with cryptographic hash-chain integrity verification."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.text import Text

from nayraastra.cli.keybindings import GLOBAL_KEY_HINTS, KEY_BACK_ESC, KEY_BACK_ZERO, KEY_SEARCH
from nayraastra.cli.navigation import Navigation, Pop, Screen, Stay
from nayraastra.cli.rendering import (
    render_breadcrumb,
    render_error_panel,
    render_footer_hints,
)
from nayraastra.cli.widgets.prompts import prompt_field
from nayraastra.cli.widgets.tables import render_audit_table
from nayraastra.core.audit.models import AuditEntry
from nayraastra.runtime import verify_chain

if TYPE_CHECKING:
    from rich.console import Console

    from nayraastra.cli.input import InputDriver
    from nayraastra.cli.state import SessionState
    from nayraastra.runtime import Runtime


class AuditScreen(Screen):
    """Displays chronological immutable audit log entries with live hash-chain verification."""

    title = "Audit Log & Chain Integrity"
    breadcrumb_title = "Audit"

    def __init__(self, page_size: int = 15) -> None:
        self.page_size = page_size
        self.page: int = 1
        self.filter_query: str = ""
        self.notice: str | None = None

    def render(self, state: SessionState, console: Console) -> None:
        console.print(render_breadcrumb(["NAYRAASTRA", "Tasks & Audit Log", "Audit Trail"]))

        if self.notice:
            console.print(render_error_panel(self.notice, title="Notice"))
            self.notice = None

        if not state.session:
            console.print(render_error_panel("No active engagement session open."))
            console.print(render_footer_hints(GLOBAL_KEY_HINTS))
            return

        # Fetch all entries for hash chain verification
        entries: list[AuditEntry] = state.session.audit.sink.get_all_entries()
        report = verify_chain(entries)

        # Hash chain status badge
        if report.valid:
            status_text = Text(
                f"✓ HASH-CHAIN VALID: {report.count} entries verified (Genesis → Head unbroken)",
                style="bold green",
            )
            badge_panel = Panel(status_text, border_style="green", padding=(0, 1))
        else:
            status_text = Text(
                f"✗ HASH-CHAIN BROKEN at entry #{report.first_broken_index}!\n{report.error_message}",
                style="bold red",
            )
            badge_panel = Panel(
                status_text,
                title="[bold red]Integrity Compromise Detected[/bold red]",
                border_style="red",
                padding=(0, 1),
            )
        console.print(badge_panel)

        # Pagination and filtering
        filtered = entries
        if self.filter_query:
            q = self.filter_query.lower()
            filtered = [
                e
                for e in entries
                if q
                in f"{e.event_type} {e.actor} {e.entity_type} {e.entity_id} {e.entry_hash}".lower()
            ]

        total_pages = max(1, (len(filtered) + self.page_size - 1) // self.page_size)
        self.page = max(1, min(self.page, total_pages))

        start_idx = (self.page - 1) * self.page_size
        page_slice = filtered[start_idx : start_idx + self.page_size]

        console.print(render_audit_table(page_slice, filter_query=""))

        # Pager controls
        pager = Text()
        pager.append(
            f"\nPage {self.page} of {total_pages} (Total: {len(filtered)} entries)  ",
            style="bold white",
        )
        pager.append("[n] Next page  ", style="bold cyan")
        pager.append("[p] Prev page  ", style="bold cyan")
        pager.append("[/] Filter  ", style="bold yellow")
        pager.append("[0/Esc] Back\n", style="bold yellow")
        console.print(pager)

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

        if ch == KEY_SEARCH:
            q = await prompt_field(driver, "Filter audit events", required=False)
            self.filter_query = q or ""
            self.page = 1
            return Stay()

        if ch == "n":
            self.page += 1
            return Stay()

        if ch == "p":
            self.page = max(1, self.page - 1)
            return Stay()

        return Stay()
