"""Status bar view model and Prompt Toolkit toolbar integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nayraastra.cli.state import SessionState


@dataclass(frozen=True)
class StatusBarViewModel:
    """Plain data representation of the persistent status bar."""

    engagement_name: str
    scope_count: int
    max_intrusiveness: str
    disruptive_enabled: bool
    dry_run: bool
    running_tasks: int
    queued_tasks: int
    failed_tasks: int
    window_status: str
    is_dev: bool

    def to_toolbar_string(self) -> str:
        """Render to single-line plain string with status delimiters."""
        eng_part = (
            f"Engagement: {self.engagement_name} (Scope: {self.scope_count})"
            if self.engagement_name != "none"
            else "No Engagement"
        )
        disruptive = " [DISRUPTIVE ENABLED]" if self.disruptive_enabled else ""
        roe_part = f"ROE: {self.max_intrusiveness}{disruptive}"
        dry_part = f"DRY-RUN: {'ON' if self.dry_run else 'OFF'}"
        tasks_part = (
            f"Tasks: {self.running_tasks} run / {self.queued_tasks} q / {self.failed_tasks} fail"
        )
        win_part = f"Window: {self.window_status}"
        dev_part = " | [DEV]" if self.is_dev else ""

        return f"{eng_part} | {roe_part} | {dry_part} | {tasks_part} | {win_part}{dev_part}"


def build_status_bar_view_model(state: SessionState) -> StatusBarViewModel:
    """Extract view-model from active session state."""
    eng_name = state.engagement.name if state.engagement else "none"
    scope_cnt = len(state.scope_entries) if state.engagement else 0
    max_int = (
        state.engagement.roe.max_intrusiveness.value
        if (state.engagement and state.engagement.roe)
        else "active-safe"
    )
    disruptive = (
        state.engagement.roe.disruptive_enabled
        if (state.engagement and state.engagement.roe)
        else False
    )

    return StatusBarViewModel(
        engagement_name=eng_name,
        scope_count=scope_cnt,
        max_intrusiveness=max_int,
        disruptive_enabled=disruptive,
        dry_run=state.dry_run,
        running_tasks=state.running_tasks_count,
        queued_tasks=state.queued_tasks_count,
        failed_tasks=state.failed_tasks_count,
        window_status=state.window_status,
        is_dev=state.is_dev,
    )
