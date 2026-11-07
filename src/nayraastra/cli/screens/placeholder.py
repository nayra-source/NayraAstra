"""Placeholder screen for roadmap capabilities planned in future phases."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.text import Text

from nayraastra.cli.keybindings import GLOBAL_KEY_HINTS, KEY_BACK_ESC, KEY_BACK_ZERO
from nayraastra.cli.navigation import Navigation, Pop, Screen, Stay
from nayraastra.cli.rendering import render_breadcrumb, render_footer_hints, safe_text

if TYPE_CHECKING:
    from rich.console import Console

    from nayraastra.cli.input import InputDriver
    from nayraastra.cli.state import SessionState
    from nayraastra.runtime import Runtime


class PlaceholderScreen(Screen):
    """Displays a planned roadmap capability panel with back navigation."""

    def __init__(self, title: str, phase_label: str, description: str) -> None:
        self.title = title
        self.breadcrumb_title = title
        self.phase_label = phase_label
        self.description = description

    def render(self, state: SessionState, console: Console) -> None:
        console.print(render_breadcrumb(["NAYRAASTRA", self.title]))

        body = Text()
        body.append(f"\n{safe_text(self.title)}\n", style="bold white")
        body.append(f"Status: Planned for {safe_text(self.phase_label)}\n\n", style="bold cyan")
        body.append(safe_text(self.description), style="dim")
        body.append("\n\nPress 0 or Esc to return to the previous menu.\n", style="dim italic")

        panel = Panel(
            body,
            title="[bold cyan]Roadmap Feature[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        )
        console.print(panel)
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
