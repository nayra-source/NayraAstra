"""Numbered menu widget with SEToolkit-style formatting and locked item badges."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

from nayraastra.cli.rendering import safe_text


@dataclass(frozen=True)
class MenuItem:
    """A selectable numbered menu item."""

    key: str
    label: str
    badge: str | None = None
    locked: bool = False
    lock_reason: str | None = None


def render_menu(
    items: Sequence[MenuItem],
    *,
    title: str | None = None,
    filter_query: str = "",
) -> RenderableType:
    """Render a clean, aligned SEToolkit-style numbered menu table."""
    table = Table(
        show_header=False,
        box=None,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("Key", justify="right", width=5, no_wrap=True)
    table.add_column("Item", ratio=1)

    query = filter_query.lower().strip()

    for item in items:
        # If filtering is active, skip items not matching query (except '0' Back/Exit)
        if query and item.key != "0":
            searchable = f"{item.label} {item.badge or ''} {item.lock_reason or ''}".lower()
            if query not in searchable:
                continue

        # Key styling
        key_text = Text()
        if item.key == "0":
            key_text.append(f"{item.key})", style="bold yellow")
        elif item.locked:
            key_text.append(f"{item.key})", style="dim")
        else:
            key_text.append(f"{item.key})", style="bold cyan")

        # Label styling
        label_text = Text()
        label_safe = safe_text(item.label)

        if item.locked:
            label_text.append(label_safe, style="dim white")
            reason = safe_text(item.lock_reason or "locked")
            label_text.append(f"  [locked: {reason}]", style="dim yellow")
        else:
            label_text.append(label_safe, style="bold white")
            if item.badge:
                badge_safe = safe_text(item.badge)
                label_text.append(f"  ({badge_safe})", style="dim")

        table.add_row(key_text, label_text)

    return table
