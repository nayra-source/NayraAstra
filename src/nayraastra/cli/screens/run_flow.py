"""Interactive Run Flow: target selection, plan preview, live progress, and results."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nayraastra.cli.keybindings import KEY_BACK_ZERO, KEY_CANCEL
from nayraastra.cli.navigation import Navigation, Pop, Screen, Stay
from nayraastra.cli.rendering import (
    render_breadcrumb,
    render_error_panel,
    render_footer_hints,
    safe_text,
)
from nayraastra.cli.widgets.confirm import prompt_disruptive_confirmation
from nayraastra.cli.widgets.progress import LiveProgressView
from nayraastra.cli.widgets.tables import render_observations_table
from nayraastra.core.domain.models import Target, Task
from nayraastra.core.domain.types import Capability, Intrusiveness, TaskStatus
from nayraastra.core.events.models import TaskFailed, TaskOutput, TaskStarted, TaskSucceeded
from nayraastra.runtime import Runtime, ValidationFailure, normalize_target

if TYPE_CHECKING:
    from nayraastra.cli.input import InputDriver
    from nayraastra.cli.state import SessionState


class RunFlowScreen(Screen):
    """Orchestrates target selection, authorization pre-check, plan preview, execution, and results."""

    def __init__(
        self,
        module_name: str,
        capability: Capability,
        capability_label: str,
        adapter: Any,
    ) -> None:
        self.module_name = module_name
        self.capability = capability
        self.capability_label = capability_label
        self.adapter = adapter
        self.title = f"Run {capability.value}"
        self.breadcrumb_title = capability.value

        self.step: int = 1  # 1: Target, 2: Params, 3: Preview, 4: Live Run, 5: Results
        self.target: Target | None = None
        self.params: dict[str, Any] = {}
        self.executed_task: Task | None = None
        self.notice: str | None = None

    def render(self, state: SessionState, console: Console) -> None:
        console.print(render_breadcrumb(["NAYRAASTRA", self.module_name, self.capability_label]))

        if self.notice:
            console.print(render_error_panel(self.notice, title="Notice"))
            self.notice = None

        if self.step == 1:
            self._render_target_selection(state, console)
        elif self.step == 3:
            self._render_plan_preview(state, console)
        elif self.step == 5 and self.executed_task:
            self._render_result_view(state, console)

        console.print(render_footer_hints((("[0]", "Cancel / Back"), ("[Ctrl+C]", "Abort"))))

    def _render_target_selection(self, state: SessionState, console: Console) -> None:
        table = Table(
            title="Select Target from In-Scope Entries",
            show_header=True,
            header_style="bold cyan",
            expand=True,
        )
        table.add_column("#", width=4, justify="right", style="dim")
        table.add_column("Kind", width=14, style="cyan")
        table.add_column("Target Value", ratio=1)
        table.add_column("Scope", width=14, justify="center")

        in_scope_entries = [e for e in state.scope_entries if e.in_scope]
        for idx, entry in enumerate(in_scope_entries, 1):
            table.add_row(
                str(idx),
                safe_text(entry.kind.value),
                safe_text(entry.value),
                "[green]IN-SCOPE[/green]",
            )

        console.print(table)
        console.print(
            Panel(
                Text(
                    "Choose an in-scope target by number, or type any target address/CIDR directly.\n"
                    "Note: Any target entered will be strictly validated against the Scope Guard.",
                    style="dim",
                ),
                padding=(0, 1),
            )
        )

    def _render_plan_preview(self, state: SessionState, console: Console) -> None:
        if not self.target or not state.engagement:
            return

        now = state.session.scheduler.clock.now() if state.session else None
        preview_task = Task(
            id="preview",
            engagement_id=state.engagement.id,
            module_name=self.module_name,
            adapter_name=self.adapter.name,
            capability=self.capability,
            target=self.target,
            intrusiveness=self.adapter.intrusiveness,
            args=dict(self.params),
            created_at=now or state.engagement.created_at,
        )

        try:
            cmd = self.adapter.build_command(preview_task)
            cmd_str = " ".join(cmd)
        except Exception as exc:
            cmd_str = f"<Error building command: {exc}>"

        estimate = self.adapter.estimate(preview_task)

        table = Table(title="Execution Plan Preview", show_header=False, box=None, padding=(0, 1))
        table.add_column("Field", style="bold cyan", width=22)
        table.add_column("Value", style="white")

        table.add_row("Capability:", safe_text(self.capability.value))
        table.add_row("Target:", safe_text(self.target.raw))
        table.add_row("Adapter:", safe_text(self.adapter.name))
        table.add_row("Intrusiveness:", safe_text(self.adapter.intrusiveness.value))
        table.add_row("Command Line:", f"[yellow]{safe_text(cmd_str)}[/yellow]")
        table.add_row("Estimated Duration:", f"{estimate.estimated_seconds:.1f}s")
        table.add_row(
            "Dry Run Mode:",
            "ON (Simulate only)" if state.dry_run or self.params.get("dry_run") else "OFF",
        )

        console.print(
            Panel(
                table,
                title="[bold green]Plan Details[/bold green]",
                border_style="green",
                padding=(0, 1),
            )
        )

    def _render_result_view(self, state: SessionState, console: Console) -> None:
        task = self.executed_task
        if not task:
            return

        st = task.status.value.upper()
        if task.status == TaskStatus.SUCCEEDED:
            status_panel = Panel(
                Text(f"Task SUCCEEDED (exit code {task.exit_code or 0})", style="bold green"),
                border_style="green",
                padding=(0, 1),
            )
        elif task.status == TaskStatus.BLOCKED:
            status_panel = Panel(
                Text(f"Task BLOCKED by Scope Guard:\n{task.error_message}", style="bold red"),
                title="[bold red]Safety Gate Denial[/bold red]",
                border_style="red",
                padding=(0, 1),
            )
        elif task.status == TaskStatus.SKIPPED:
            status_panel = Panel(
                Text(
                    "Task SKIPPED (Dry-Run Mode: plan verified, adapter skipped)",
                    style="bold yellow",
                ),
                border_style="yellow",
                padding=(0, 1),
            )
        else:
            status_panel = Panel(
                Text(f"Task {st}: {task.error_message or 'Unknown error'}", style="bold red"),
                border_style="red",
                padding=(0, 1),
            )
        console.print(status_panel)

        # Artifacts and Observations
        if state.session:
            obs = state.session.scheduler.obs_repo.list_by_task(task.id)
            if obs:
                console.print(render_observations_table(obs))

            artifacts = state.session.scheduler.artifact_repo.list_by_task(task.id)
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

    async def handle(
        self,
        input_str: str,
        state: SessionState,
        driver: InputDriver,
        runtime: Runtime,
    ) -> Navigation:
        ch = input_str.strip()

        if ch in (KEY_BACK_ZERO, KEY_CANCEL):
            return Pop()

        if self.step == 1:
            return await self._handle_target_input(ch, state, driver, runtime)
        if self.step == 3:
            return await self._handle_plan_confirmation(ch, state, driver, runtime)
        if self.step == 5:
            # Result screen: any key or 0 pops back to module menu
            return Pop()

        return Stay()

    async def _handle_target_input(
        self,
        ch: str,
        state: SessionState,
        driver: InputDriver,
        runtime: Runtime,
    ) -> Navigation:
        in_scope_entries = [e for e in state.scope_entries if e.in_scope]
        selected_raw: str | None = None

        if ch.isdigit():
            idx = int(ch) - 1
            if 0 <= idx < len(in_scope_entries):
                selected_raw = in_scope_entries[idx].value

        if not selected_raw:
            # User typed target string directly
            selected_raw = ch

        try:
            self.target = normalize_target(selected_raw)
        except ValidationFailure as exc:
            self.notice = f"Invalid target: {exc}"
            return Stay()

        if state.dry_run:
            self.params["dry_run"] = True

        self.step = 3
        return Stay()

    async def _handle_plan_confirmation(
        self,
        ch: str,
        state: SessionState,
        driver: InputDriver,
        runtime: Runtime,
    ) -> Navigation:
        if not state.session or not state.engagement or not self.target:
            return Pop()

        if ch.lower() in (KEY_BACK_ZERO, "n", "no", "q"):
            return Pop()

        # Check disruptive double opt-in if applicable
        if self.adapter.intrusiveness == Intrusiveness.DISRUPTIVE:
            confirmed = await prompt_disruptive_confirmation(
                driver, Console(), state.engagement.name
            )
            if not confirmed:
                self.notice = "Disruptive confirmation aborted."
                return Pop()
        elif ch.lower() not in ("y", "yes", "1"):
            self.notice = "Enter 'y' to confirm or '0' to cancel."
            return Stay()

        # Enqueue task
        task = state.session.tasks.queue(
            engagement=state.engagement,
            capability=self.capability,
            target=self.target,
            params=self.params,
            adapter_name=self.adapter.name,
        )

        progress_view = LiveProgressView(
            task_id=task.id,
            capability=self.capability.value,
            target=self.target.raw,
            adapter=self.adapter.name,
        )

        live_ref: list[Live] = []

        # Event Bus subscription for live output
        def _on_started(event: TaskStarted) -> None:
            if event.task_id == task.id:
                progress_view.set_running()
                if live_ref:
                    live_ref[0].update(progress_view.render())

        def _on_output(event: TaskOutput) -> None:
            if event.task_id == task.id:
                progress_view.append_output(event.line)
                if live_ref:
                    live_ref[0].update(progress_view.render())

        def _on_succeeded(event: TaskSucceeded) -> None:
            if event.task_id == task.id:
                progress_view.set_finished("SUCCEEDED")
                if live_ref:
                    live_ref[0].update(progress_view.render())

        def _on_failed(event: TaskFailed) -> None:
            if event.task_id == task.id:
                progress_view.set_finished("FAILED")
                if live_ref:
                    live_ref[0].update(progress_view.render())

        unsub_start = state.session.events.subscribe(TaskStarted, _on_started)
        unsub_output = state.session.events.subscribe(TaskOutput, _on_output)
        unsub_succ = state.session.events.subscribe(TaskSucceeded, _on_succeeded)
        unsub_fail = state.session.events.subscribe(TaskFailed, _on_failed)

        console = Console()
        try:
            with Live(progress_view.render(), console=console, refresh_per_second=4) as live:
                live_ref.append(live)
                progress_view.set_running()
                live.update(progress_view.render())

                # If task was already blocked at enqueue time, no need to dispatch to scheduler
                if task.status != TaskStatus.BLOCKED:
                    task = await state.session.scheduler.execute_task(task.id)

                progress_view.set_finished(task.status.value)
                live.update(progress_view.render())
        except (KeyboardInterrupt, asyncio.CancelledError):
            state.session.scheduler.cancel(task.id)
            self.notice = "Task was cancelled by user."
            return Pop()
        finally:
            live_ref.clear()
            unsub_start.unsubscribe()
            unsub_output.unsubscribe()
            unsub_succ.unsubscribe()
            unsub_fail.unsubscribe()

        self.executed_task = state.session.tasks.task_repo.get(task.id) or task
        state.refresh_tasks()
        self.step = 5
        return Stay()
