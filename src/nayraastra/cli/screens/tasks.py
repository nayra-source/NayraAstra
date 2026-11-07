"""Tasks execution history, filtering, and detail inspection screens."""

from __future__ import annotations

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
from nayraastra.cli.screens.audit import AuditScreen
from nayraastra.cli.widgets.prompts import prompt_field
from nayraastra.cli.widgets.tables import render_observations_table, render_tasks_table
from nayraastra.core.domain.models import Task
from nayraastra.core.domain.types import TaskStatus

if TYPE_CHECKING:
    from rich.console import Console

    from nayraastra.cli.input import InputDriver
    from nayraastra.cli.state import SessionState
    from nayraastra.runtime import Runtime


class TasksScreen(Screen):
    """Tasks history table with status filter, search, detail view, and audit log link."""

    title = "Tasks & Audit Log"
    breadcrumb_title = "Tasks"

    def __init__(self) -> None:
        self.notice: str | None = None
        self.filter_query: str = ""
        self.status_filter: TaskStatus | None = None

    def render(self, state: SessionState, console: Console) -> None:
        console.print(render_breadcrumb(["NAYRAASTRA", "Tasks & Audit Log"]))

        if self.notice:
            console.print(render_error_panel(self.notice, title="Notice"))
            self.notice = None

        state.refresh_tasks()
        tasks = state.tasks_cache
        if self.status_filter:
            tasks = [t for t in tasks if t.status == self.status_filter]

        console.print(render_tasks_table(tasks, filter_query=self.filter_query))

        hints = Text()
        hints.append("\nActions: ", style="bold white")
        hints.append("[1..N] View Task Detail   ", style="bold cyan")
        hints.append("[a] View Audit Trail & Hash-Chain   ", style="bold green")
        hints.append("[f] Filter by Status   ", style="bold yellow")
        hints.append("[/] Search   ", style="bold cyan")
        hints.append("[0/Esc] Back\n", style="bold yellow")
        console.print(hints)

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

        if ch.lower() == "a":
            return Push(AuditScreen())

        if ch == KEY_SEARCH:
            q = await prompt_field(
                driver, "Search tasks (by id, target, capability, error)", required=False
            )
            self.filter_query = q or ""
            return Stay()

        if ch.lower() == "f":
            st_choice = await prompt_field(
                driver,
                "Status filter: (1: all, 2: succeeded, 3: blocked, 4: failed, 5: running)",
                default="1",
            )
            mapping = {
                "2": TaskStatus.SUCCEEDED,
                "3": TaskStatus.BLOCKED,
                "4": TaskStatus.FAILED,
                "5": TaskStatus.RUNNING,
            }
            self.status_filter = mapping.get(st_choice or "1")
            return Stay()

        if ch.isdigit():
            tasks = state.tasks_cache
            if self.status_filter:
                tasks = [t for t in tasks if t.status == self.status_filter]
            if self.filter_query:
                q = self.filter_query.lower()
                tasks = [
                    t
                    for t in tasks
                    if q in f"{t.id} {t.capability.value} {t.target.raw} {t.status.value}".lower()
                ]

            idx = int(ch) - 1
            if 0 <= idx < len(tasks):
                return Push(TaskDetailScreen(tasks[idx]))

        return Stay()


class TaskDetailScreen(Screen):
    """Detailed inspector for a single task including artifacts, command, and observations."""

    def __init__(self, task: Task) -> None:
        self.task = task
        self.title = f"Task {task.id[:8]}"
        self.breadcrumb_title = f"Task {task.id[:8]}"

    def render(self, state: SessionState, console: Console) -> None:
        console.print(render_breadcrumb(["NAYRAASTRA", "Tasks", f"Task {self.task.id[:8]}"]))

        table = Table(title="Task Metadata", show_header=False, box=None, padding=(0, 1))
        table.add_column("Property", style="bold cyan", width=20)
        table.add_column("Value", style="white")

        table.add_row("Task ID:", safe_text(self.task.id))
        table.add_row("Capability:", safe_text(self.task.capability.value))
        table.add_row("Adapter:", safe_text(self.task.adapter_name))
        table.add_row("Target:", safe_text(self.task.target.raw))
        table.add_row("Status:", safe_text(self.task.status.value.upper()))
        table.add_row(
            "Exit Code:", str(self.task.exit_code) if self.task.exit_code is not None else "-"
        )

        if self.task.error_message:
            table.add_row("Error / Policy:", f"[red]{safe_text(self.task.error_message)}[/red]")

        console.print(Panel(table, title="[bold cyan]Details[/bold cyan]", padding=(0, 1)))

        if state.session:
            obs = state.session.scheduler.obs_repo.list_by_task(self.task.id)
            if obs:
                console.print(render_observations_table(obs))

            artifacts = state.session.scheduler.artifact_repo.list_by_task(self.task.id)
            if artifacts:
                art_table = Table(
                    title="Generated Artifacts", show_header=True, header_style="bold cyan"
                )
                art_table.add_column("Path", ratio=1)
                art_table.add_column("Size (bytes)", width=14, justify="right")
                art_table.add_column("SHA-256 Digest", width=20, style="dim")
                for a in artifacts:
                    art_table.add_row(
                        safe_text(a.path), str(a.size_bytes), safe_text(a.sha256[:16] + "...")
                    )
                console.print(art_table)

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
