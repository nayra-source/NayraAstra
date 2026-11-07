"""Rendering helpers, untrusted string sanitization, and layout components."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from rich.console import Console, RenderableType
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

from nayraastra.cli.theme import CLI_THEME

if TYPE_CHECKING:
    from nayraastra.cli.state import SessionState

# Regex for stripping ANSI escape sequences
_ANSI_REGEX = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# Dangerous Unicode directional override characters
_BIDI_CHARS = {
    "\u202a",  # Left-to-Right Embedding
    "\u202b",  # Right-to-Left Embedding
    "\u202c",  # Pop Directional Formatting
    "\u202d",  # Left-to-Right Override
    "\u202e",  # Right-to-Left Override
    "\u2066",  # Left-to-Right Isolate
    "\u2067",  # Right-to-Left Isolate
    "\u2068",  # First Strong Isolate
    "\u2069",  # Pop Directional Isolate
}


def safe_text(raw: object, *, allow_newlines: bool = False) -> str:
    """Sanitize an untrusted string to render safely in Rich without terminal injection.

    1. Convert to string.
    2. Strip ANSI escape sequences.
    3. Remove NUL bytes and Unicode bidi override characters.
    4. Strip non-printable control characters (preserving tab/newline if allowed).
    5. Escape Rich markup syntax so tokens like '[red]' are rendered literally.
    """
    if raw is None:
        return ""
    text = str(raw)

    # 1. Strip ANSI escape sequences
    text = _ANSI_REGEX.sub("", text)

    # 2. Remove NUL and Bidi override characters
    text = text.replace("\x00", "")
    for ch in _BIDI_CHARS:
        text = text.replace(ch, "")

    # 3. Strip control characters
    cleaned_chars: list[str] = []
    for char in text:
        code = ord(char)
        if char == "\n" and allow_newlines:
            cleaned_chars.append("\n")
        elif char == "\t":
            cleaned_chars.append("    ")
        elif code < 32 or (127 <= code <= 159):
            # Non-printable control char
            continue
        else:
            cleaned_chars.append(char)
    cleaned = "".join(cleaned_chars)

    # 4. Escape Rich markup
    return escape(cleaned)


def create_console(*, plain: bool = False, no_color: bool = False) -> Console:
    """Create a Rich Console configured for application theme and plain-text flags."""
    return Console(
        theme=CLI_THEME,
        no_color=no_color or plain,
        highlight=not plain,
        soft_wrap=False,
    )


def render_breadcrumb(breadcrumbs: Sequence[str]) -> RenderableType:
    """Render a standard breadcrumb header e.g. NAYRAASTRA > Recon > Port Scan."""
    text = Text()
    for idx, segment in enumerate(breadcrumbs):
        if idx > 0:
            text.append(" › ", style="dim")
        if idx == len(breadcrumbs) - 1:
            text.append(safe_text(segment), style="bold white")
        else:
            text.append(safe_text(segment), style="dim cyan")
    return Panel(
        text,
        style="bold white on dark_blue",
        padding=(0, 1),
    )


def render_footer_hints(hints: Sequence[tuple[str, str]]) -> Text:
    """Render a horizontal key-hint line e.g. [0/Esc] Back  [?] Help."""
    footer = Text()
    for idx, (key, label) in enumerate(hints):
        if idx > 0:
            footer.append("   ")
        footer.append(key, style="bold cyan")
        footer.append(f" {label}", style="dim")
    return footer


def render_error_panel(message: str, *, title: str = "Error", code: str | None = None) -> Panel:
    """Render a clean error panel with optional error code."""
    content = Text()
    if code:
        content.append(f"[{code}] ", style="bold red")
    content.append(safe_text(message), style="white")
    return Panel(
        content,
        title=f"[bold red]{title}[/bold red]",
        border_style="red",
        padding=(0, 1),
    )


def render_status_bar(state: SessionState) -> str:
    """Produce plain status bar text suitable for prompt_toolkit bottom_toolbar."""
    parts: list[str] = []

    # 1. Engagement
    if state.engagement:
        name = safe_text(state.engagement.name)
        scope_count = len(state.scope_entries)
        parts.append(f"Engagement: {name} (Scope: {scope_count})")
    else:
        parts.append("No Engagement")

    # 2. Intrusiveness
    if state.engagement and state.engagement.roe:
        max_int = state.engagement.roe.max_intrusiveness.value
        disruptive = " [DISRUPTIVE ENABLED]" if state.engagement.roe.disruptive_enabled else ""
        parts.append(f"ROE: {max_int}{disruptive}")
    else:
        parts.append("ROE: active-safe")

    # 3. Dry-run
    if state.dry_run:
        parts.append("DRY-RUN: ON")
    else:
        parts.append("DRY-RUN: OFF")

    # 4. Tasks count
    running = state.running_tasks_count
    queued = state.queued_tasks_count
    failed = state.failed_tasks_count
    parts.append(f"Tasks: {running} run / {queued} q / {failed} fail")

    # 5. Window state
    parts.append(f"Window: {state.window_status}")

    # 6. DEV badge
    if state.is_dev:
        parts.append("[DEV]")

    return " | ".join(parts)
