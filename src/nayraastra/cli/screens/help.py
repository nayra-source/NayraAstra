"""Help overlay screen displaying keybindings, navigation rules, and safety guide."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nayraastra.cli.keybindings import GLOBAL_KEY_HINTS, KEY_BACK_ESC, KEY_BACK_ZERO
from nayraastra.cli.navigation import Navigation, Pop, Screen, Stay
from nayraastra.cli.rendering import render_breadcrumb, render_footer_hints

if TYPE_CHECKING:
    from rich.console import Console

    from nayraastra.cli.input import InputDriver
    from nayraastra.cli.state import SessionState
    from nayraastra.runtime import Runtime


class HelpScreen(Screen):
    """Contextual help overlay showing global shortcuts and operational rules."""

    title = "Help & Shortcuts"
    breadcrumb_title = "Help"

    def render(self, state: SessionState, console: Console) -> None:
        console.print(render_breadcrumb(["NAYRAASTRA", "Help & Shortcuts"]))

        # Keybindings table
        table = Table(
            title="Global Keyboard Controls",
            show_header=True,
            header_style="bold cyan",
            expand=True,
        )
        table.add_column("Key / Shortcut", width=16, style="bold cyan")
        table.add_column("Action", ratio=1)
        table.add_column("Scope", width=22, style="dim")

        table.add_row("0", "Back to previous screen / Exit at Main Menu", "Global")
        table.add_row("Esc", "Back to previous screen", "Global")
        table.add_row("?", "Display this help overlay", "Global")
        table.add_row("/", "Filter / search active list or table", "List & Table views")
        table.add_row("Ctrl + L", "Redraw / refresh terminal screen", "Global")
        table.add_row("Ctrl + C", "Cancel active prompt or abort running task", "Global")
        table.add_row("q", "Prompt application exit", "Main Menu")
        table.add_row("1..9", "Instant selection (when menu has ≤ 9 items)", "Menus")
        table.add_row(
            "<number> + Enter", "Multi-digit item selection (> 9 items)", "Menus & Tables"
        )

        console.print(table)

        # Safety & Navigation tips panel
        tips = Text()
        tips.append("Navigation & Safety Principles:\n\n", style="bold white")
        tips.append("• Scope Guard: ", style="bold green")
        tips.append(
            "Every target is validated against engagement scope. Out-of-scope vetoes immediately.\n"
        )
        tips.append("• Double Opt-In: ", style="bold yellow")
        tips.append(
            "Disruptive tasks require explicit opt-in in ROE and typing the engagement name.\n"
        )
        tips.append("• Untrusted Strings: ", style="bold cyan")
        tips.append(
            "All output and target strings are sanitized against ANSI/Rich markup injection.\n"
        )
        tips.append("• Back Navigation: ", style="bold magenta")
        tips.append("Press '0' or 'Esc' at any depth to return safely without losing state.\n")

        console.print(
            Panel(
                tips,
                title="[bold cyan]Operational Guidelines[/bold cyan]",
                border_style="cyan",
                padding=(0, 1),
            )
        )
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
