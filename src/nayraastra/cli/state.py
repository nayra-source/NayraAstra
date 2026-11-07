"""Session state management for the CLI shell."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from nayraastra.core.domain.models import Engagement, ScopeEntry, Task
from nayraastra.core.domain.types import TaskStatus

if TYPE_CHECKING:
    from nayraastra.runtime import Session


class SessionState:
    """Holds active session, engagement context, dry-run toggles, and filters."""

    def __init__(
        self,
        *,
        is_dev: bool = False,
        dry_run: bool = False,
        config: Any = None,
    ) -> None:
        self.is_dev = is_dev
        self.dry_run = dry_run
        self.config = config
        self.session: Session | None = None
        self.engagement: Engagement | None = None
        self.scope_entries: list[ScopeEntry] = []
        self.tasks_cache: list[Task] = []
        self.task_filter_status: TaskStatus | None = None
        self.task_search_query: str = ""
        self.audit_search_query: str = ""

    def set_session(
        self,
        session: Session | None,
        engagement: Engagement | None,
        scope_entries: list[ScopeEntry] | None = None,
    ) -> None:
        """Bind an active engagement session."""
        if self.session and self.session != session:
            self.session.close()
        self.session = session
        self.engagement = engagement
        self.scope_entries = list(scope_entries or [])
        self.refresh_tasks()

    def close_session(self) -> None:
        """Close active engagement session and clear context."""
        if self.session:
            self.session.close()
            self.session = None
        self.engagement = None
        self.scope_entries.clear()
        self.tasks_cache.clear()

    def refresh_tasks(self) -> None:
        """Refresh tasks cache from the active session."""
        if not self.session:
            self.tasks_cache.clear()
            return
        self.tasks_cache = self.session.tasks.list_by_engagement(self.session.engagement_id)

    @property
    def running_tasks_count(self) -> int:
        return sum(1 for t in self.tasks_cache if t.status == TaskStatus.RUNNING)

    @property
    def queued_tasks_count(self) -> int:
        return sum(1 for t in self.tasks_cache if t.status == TaskStatus.PENDING)

    @property
    def failed_tasks_count(self) -> int:
        return sum(1 for t in self.tasks_cache if t.status == TaskStatus.FAILED)

    @property
    def window_status(self) -> str:
        """Compute window state (active, expires in Xh, EXPIRED, unconstrained)."""
        if not self.engagement or not self.engagement.roe:
            return "unconstrained"
        roe = self.engagement.roe
        if not roe.window_start and not roe.window_end:
            return "unconstrained"

        now = datetime.now(UTC)
        if roe.window_start and now < roe.window_start:
            diff = roe.window_start - now
            mins = int(diff.total_seconds() // 60)
            return f"starts in {mins}m" if mins < 60 else f"starts in {mins // 60}h"

        if roe.window_end:
            if now > roe.window_end:
                return "EXPIRED"
            diff = roe.window_end - now
            mins = int(diff.total_seconds() // 60)
            return f"expires in {mins}m" if mins < 60 else f"expires in {mins // 60}h"

        return "active"
