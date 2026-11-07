"""Confirmation prompts including disruptive double opt-in phrase verification."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.text import Text

from nayraastra.cli.rendering import safe_text

if TYPE_CHECKING:
    from rich.console import Console

    from nayraastra.cli.input import InputDriver


async def prompt_confirmation(
    driver: InputDriver,
    console: Console,
    message: str,
    *,
    default: bool = False,
    bottom_toolbar: str | None = None,
) -> bool:
    """Prompt user for standard [y/N] or [Y/n] confirmation."""
    return await driver.confirm(message, default=default, bottom_toolbar=bottom_toolbar)


async def prompt_disruptive_confirmation(
    driver: InputDriver,
    console: Console,
    engagement_name: str,
    *,
    bottom_toolbar: str | None = None,
) -> bool:
    """Show an explicit high-visibility warning panel and require typing the exact engagement name."""
    warning = Text()
    warning.append(
        "WARNING: DISRUPTIVE OPERATION REQUESTED\n",
        style="bold red underline",
    )
    warning.append(
        "Disruptive tasks may cause network degradation, packet loss, or host instability.\n"
        "To confirm execution, you MUST type the exact engagement name below:\n\n",
        style="bold white",
    )
    warning.append(f"  Engagement Name: {safe_text(engagement_name)}\n", style="bold cyan")

    console.print(
        Panel(
            warning,
            title="[bold red]Double Opt-In Security Gate[/bold red]",
            border_style="red",
            padding=(1, 2),
        )
    )

    prompt_msg = f"Type '{engagement_name}' to confirm:"
    return await driver.confirm_phrase(
        prompt_msg,
        expected_phrase=engagement_name,
        bottom_toolbar=bottom_toolbar,
    )
