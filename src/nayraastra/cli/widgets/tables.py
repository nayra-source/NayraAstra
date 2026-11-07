"""Rich table formatters for scopes, tasks, audit logs, and observations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from rich.table import Table
from rich.text import Text

from nayraastra.cli.rendering import safe_text

if TYPE_CHECKING:
    from nayraastra.core.audit.models import AuditEntry
    from nayraastra.core.domain.models import Engagement, Observation, ScopeEntry, Task


def render_scope_table(entries: Sequence[ScopeEntry]) -> Table:
    """Format engagement scope rules into a clean Rich table."""
    table = Table(
        title="Engagement Scope Rules",
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("#", width=4, justify="right", style="dim")
    table.add_column("Kind", width=12, style="cyan")
    table.add_column("Target Value", ratio=1)
    table.add_column("Status", width=14, justify="center")
    table.add_column("Note", ratio=1, style="dim")

    if not entries:
        table.add_row("-", "none", "No scope entries defined", "[yellow]EMPTY[/yellow]", "")
        return table

    for idx, entry in enumerate(entries, 1):
        status_text = (
            Text("IN-SCOPE", style="bold green")
            if entry.in_scope
            else Text("OUT-OF-SCOPE", style="bold red")
        )
        table.add_row(
            str(idx),
            safe_text(entry.kind.value if hasattr(entry.kind, "value") else entry.kind),
            safe_text(entry.value),
            status_text,
            safe_text(entry.note),
        )
    return table


def render_tasks_table(tasks: Sequence[Task], *, filter_query: str = "") -> Table:
    """Format scheduled and completed tasks into a status-coded table."""
    table = Table(
        title="Tasks Execution History",
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("ID", width=10, style="dim")
    table.add_column("Capability", width=18, style="cyan")
    table.add_column("Target", ratio=1)
    table.add_column("Status", width=14, justify="center")
    table.add_column("Duration", width=10, justify="right")
    table.add_column("Error / Detail", ratio=1, style="dim")

    query = filter_query.lower().strip()

    count = 0
    for task in tasks:
        searchable = (
            f"{task.id} {task.capability.value} {task.target.raw} {task.status.value}".lower()
        )
        if query and query not in searchable:
            continue
        count += 1

        # Status color
        st = task.status.value
        if st == "succeeded":
            status_styled = Text("SUCCEEDED", style="bold green")
        elif st == "failed":
            status_styled = Text("FAILED", style="bold red")
        elif st == "blocked":
            status_styled = Text("BLOCKED", style="bold red")
        elif st == "running":
            status_styled = Text("RUNNING", style="bold yellow")
        elif st == "cancelled":
            status_styled = Text("CANCELLED", style="dim yellow")
        else:
            status_styled = Text(st.upper(), style="dim")

        duration_str = "-"
        if task.started_at and task.finished_at:
            dur = (task.finished_at - task.started_at).total_seconds()
            duration_str = f"{dur:.2f}s"

        err = safe_text(task.error_message or "")

        table.add_row(
            safe_text(task.id[:8]),
            safe_text(task.capability.value),
            safe_text(task.target.raw),
            status_styled,
            duration_str,
            err,
        )

    if count == 0:
        table.add_row("-", "none", "No tasks found", "[dim]NONE[/dim]", "-", "")

    return table


def render_audit_table(entries: Sequence[AuditEntry], *, filter_query: str = "") -> Table:
    """Format audit entries into a tamper-evident table."""
    table = Table(
        title="Engagement Audit Trail",
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Idx", width=5, justify="right", style="dim")
    table.add_column("Logged At (UTC)", width=20, style="dim")
    table.add_column("Event Type", width=22, style="bold white")
    table.add_column("Actor", width=14, style="cyan")
    table.add_column("Entity", width=18, style="white")
    table.add_column("Entry Hash", width=14, style="dim")

    query = filter_query.lower().strip()

    count = 0
    for idx, entry in enumerate(entries, 1):
        searchable = (
            f"{entry.event_type} {entry.actor} {entry.entity_type} {entry.entity_id}".lower()
        )
        if query and query not in searchable:
            continue
        count += 1

        entity_info = (
            f"{entry.entity_type}:{entry.entity_id[:8]}" if entry.entity_id else entry.entity_type
        )
        time_str = safe_text(str(entry.logged_at))

        table.add_row(
            str(idx),
            time_str,
            safe_text(entry.event_type),
            safe_text(entry.actor),
            safe_text(entity_info),
            safe_text(entry.entry_hash[:10] + "..."),
        )

    if count == 0:
        table.add_row("-", "-", "No audit events recorded", "-", "-", "-")

    return table


def render_observations_table(observations: Sequence[Observation]) -> Table:
    """Format structured observations extracted from task results."""
    table = Table(
        title="Extracted Observations",
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Key", width=18, style="bold cyan")
    table.add_column("Target", width=20, style="white")
    table.add_column("Confidence", width=12, justify="center")
    table.add_column("Value / Metadata", ratio=1)

    if not observations:
        table.add_row("-", "-", "-", "No observations generated")
        return table

    for obs in observations:
        conf_str = safe_text(str(obs.confidence))
        target_str = str(obs.value.get("address") or obs.value.get("target") or "-")
        val_summary = ", ".join(f"{k}={v}" for k, v in obs.value.items() if k != "task_id")
        table.add_row(
            safe_text(obs.observation_key),
            safe_text(target_str),
            conf_str,
            safe_text(val_summary),
        )

    return table


def render_engagements_table(
    engagements: Sequence[Engagement],
    *,
    filter_query: str = "",
) -> Table:
    """Format engagement records for the Load screen."""
    table = Table(
        title="Known Engagements",
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("#", width=4, justify="right", style="dim")
    table.add_column("ID", width=10, style="dim")
    table.add_column("Name", ratio=1, style="bold white")
    table.add_column("Client", width=18, style="cyan")
    table.add_column("Status", width=12, justify="center")
    table.add_column("Created", width=20, style="dim")

    query = filter_query.lower().strip()

    count = 0
    for idx, eng in enumerate(engagements, 1):
        searchable = f"{eng.id} {eng.name} {eng.client} {eng.status}".lower()
        if query and query not in searchable:
            continue
        count += 1

        st = eng.status.upper()
        st_styled = Text(st, style="bold green" if st == "ACTIVE" else "dim yellow")
        created_str = eng.created_at.strftime("%Y-%m-%d %H:%M:%S")

        table.add_row(
            str(idx),
            safe_text(eng.id[:8]),
            safe_text(eng.name),
            safe_text(eng.client or "-"),
            st_styled,
            created_str,
        )

    if count == 0:
        table.add_row("-", "-", "No engagements found", "-", "-", "-")

    return table
