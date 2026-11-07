"""Live progress panel for streaming task execution output via Rich Live."""

from __future__ import annotations

import collections
import time

from rich.console import RenderableType
from rich.panel import Panel
from rich.text import Text

from nayraastra.cli.rendering import safe_text


class LiveProgressView:
    """Manages streaming terminal output and status display during task execution."""

    def __init__(
        self,
        task_id: str,
        capability: str,
        target: str,
        adapter: str,
        *,
        max_lines: int = 12,
    ) -> None:
        self.task_id = task_id
        self.capability = capability
        self.target = target
        self.adapter = adapter
        self.max_lines = max_lines
        self.lines: collections.deque[str] = collections.deque(maxlen=max_lines)
        self.status: str = "PENDING"
        self.start_time: float = time.monotonic()
        self.end_time: float | None = None

    def set_running(self) -> None:
        self.status = "RUNNING"
        self.start_time = time.monotonic()

    def set_finished(self, status: str) -> None:
        self.status = status
        self.end_time = time.monotonic()

    def append_output(self, line: str) -> None:
        """Sanitize untrusted line and append to bounded scrollback."""
        clean = safe_text(line, allow_newlines=False)
        if clean:
            self.lines.append(clean)

    def render(self) -> RenderableType:
        """Render a Rich Panel with header metadata and bounded output scrollback."""
        elapsed = (self.end_time or time.monotonic()) - self.start_time

        header = Text()
        header.append(f"Task: {self.task_id[:8]} | ", style="dim")
        header.append(f"{self.capability} › {self.target} | ", style="bold white")
        header.append(f"Adapter: {self.adapter} | ", style="cyan")

        if self.status == "RUNNING":
            header.append("STATUS: RUNNING", style="bold yellow")
        elif self.status == "SUCCEEDED":
            header.append("STATUS: SUCCEEDED", style="bold green")
        elif self.status in ("FAILED", "BLOCKED"):
            header.append(f"STATUS: {self.status}", style="bold red")
        else:
            header.append(f"STATUS: {self.status}", style="dim")

        header.append(f" ({elapsed:.1f}s)", style="dim")

        body = Text()
        if not self.lines:
            body.append("Executing adapter command... (waiting for output)", style="dim italic")
        else:
            for idx, line in enumerate(self.lines):
                if idx > 0:
                    body.append("\n")
                body.append(line)

        border = (
            "yellow"
            if self.status == "RUNNING"
            else ("green" if self.status == "SUCCEEDED" else "red")
        )
        return Panel(
            body,
            title=header,
            border_style=border,
            padding=(0, 1),
        )
