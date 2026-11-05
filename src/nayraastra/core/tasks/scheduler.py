"""Sequential asyncio task scheduler and execution pipeline."""

from __future__ import annotations

import asyncio
import logging

from nayraastra.core.audit.logger import AuditLogger
from nayraastra.core.audit.models import AuditEventType
from nayraastra.core.config import ExecutionConfig
from nayraastra.core.domain.models import Task
from nayraastra.core.domain.time_id import Clock
from nayraastra.core.domain.types import TaskStatus, assert_transition, can_transition
from nayraastra.core.events.bus import EventBus
from nayraastra.core.events.models import (
    ScopeViolation,
    TaskBlocked,
    TaskFailed,
    TaskOutput,
    TaskStarted,
    TaskSucceeded,
    ToolMissing,
)
from nayraastra.core.ports import (
    AdapterRegistryPort,
    ArtifactRepository,
    EngagementRepository,
    ObservationRepository,
    RunContext,
    ScopeRepository,
    TaskRepository,
    WorkspaceProvider,
)
from nayraastra.core.scope.authorizer import TaskAuthorizer
from nayraastra.core.scope.guard import ScopeGuard
from nayraastra.core.tasks.rate_limiter import AsyncRateLimiter

logger = logging.getLogger("nayraastra.scheduler")


class Scheduler:
    """Sequential executor for pentesting tasks (Phase 1 single-worker guarantee)."""

    def __init__(
        self,
        task_repo: TaskRepository,
        scope_repo: ScopeRepository,
        eng_repo: EngagementRepository,
        artifact_repo: ArtifactRepository,
        obs_repo: ObservationRepository,
        registry: AdapterRegistryPort,
        authorizer: TaskAuthorizer,
        audit: AuditLogger,
        events: EventBus,
        workspace_provider: WorkspaceProvider,
        clock: Clock,
        execution_config: ExecutionConfig | None = None,
    ) -> None:
        self.task_repo = task_repo
        self.scope_repo = scope_repo
        self.eng_repo = eng_repo
        self.artifact_repo = artifact_repo
        self.obs_repo = obs_repo
        self.registry = registry
        self.authorizer = authorizer
        self.audit = audit
        self.events = events
        self.workspace_provider = workspace_provider
        self.clock = clock
        self.cfg = execution_config or ExecutionConfig()

        if self.cfg.max_parallel_tasks > 1:
            logger.warning(
                "Phase 1 requires sequential execution. Clamping max_parallel_tasks=%d to 1.",
                self.cfg.max_parallel_tasks,
            )

        self.rate_limiter = AsyncRateLimiter(self.cfg.rate_limit_per_second)
        self._active_cancels: dict[str, asyncio.Event] = {}
        self._queue_lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()

    def find_interrupted_tasks(self) -> list[Task]:
        """List tasks stuck in RUNNING state (e.g. from a prior crash)."""
        return self.task_repo.find_interrupted()

    def cancel(self, task_id: str) -> bool:
        """Signal cancellation for an active or pending task."""
        if task_id in self._active_cancels:
            self._active_cancels[task_id].set()

        task = self.task_repo.get(task_id)
        if task and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            now = self.clock.now()
            assert_transition(task.status, TaskStatus.CANCELLED)
            self.task_repo.update_status(
                task_id,
                TaskStatus.CANCELLED,
                finished_at=now,
                error_message="Task cancelled by user.",
            )
            self.audit.log(
                event_type=AuditEventType.TASK_CANCELLED,
                entity_type="task",
                entity_id=task_id,
                payload={"previous_status": task.status.value},
            )
            return True
        return False

    async def execute_task(self, task_id: str) -> Task:
        """Run the end-to-end execution pipeline for a single task."""
        async with self._queue_lock:
            task = self.task_repo.get(task_id)
            if not task:
                raise ValueError(f"Task {task_id!r} not found.")

            if task.status != TaskStatus.PENDING:
                return task

            await self.rate_limiter.acquire()

            # 1. Re-authorize at execution time
            engagement = self.eng_repo.get(task.engagement_id)
            if not engagement:
                self._fail_task(task, f"Engagement {task.engagement_id} not found.")
                return self.task_repo.get(task_id) or task

            scope_entries = self.scope_repo.list_entries(task.engagement_id)
            guard = ScopeGuard(scope_entries)
            auth_decision = self.authorizer.authorize(
                engagement=engagement,
                scope_guard=guard,
                target=task.target,
                capability=task.capability,
                intrusiveness=task.intrusiveness,
            )

            if not auth_decision.allowed:
                err_msg = "; ".join(auth_decision.violations)
                assert_transition(task.status, TaskStatus.BLOCKED)
                self.task_repo.update_status(task_id, TaskStatus.BLOCKED, error_message=err_msg)
                self.audit.log(
                    event_type=AuditEventType.POLICY_DENIED,
                    entity_type="task",
                    entity_id=task_id,
                    payload={"violations": auth_decision.violations},
                )
                self.audit.log(
                    event_type=AuditEventType.TASK_BLOCKED,
                    entity_type="task",
                    entity_id=task_id,
                    payload={"reason": err_msg},
                )
                self.events.publish(
                    ScopeViolation(
                        engagement_id=task.engagement_id,
                        target=task.target.normalized,
                        violations=auth_decision.violations,
                    )
                )
                self.events.publish(
                    TaskBlocked(
                        task_id=task_id,
                        engagement_id=task.engagement_id,
                        reason=err_msg,
                    )
                )
                return self.task_repo.get(task_id) or task

            # 2. Resolve adapter & check installed
            adapter = self.registry.get(task.adapter_name)
            if not adapter:
                self._fail_task(task, f"Adapter {task.adapter_name} not registered.")
                return self.task_repo.get(task_id) or task

            status = adapter.check_installed()
            if not status.installed:
                err = status.error or f"Tool {adapter.name} is not installed on this system."
                self.events.publish(
                    ToolMissing(
                        tool_name=adapter.name,
                        adapter_name=adapter.name,
                        error_message=err,
                    )
                )
                self._fail_task(task, err)
                return self.task_repo.get(task_id) or task

            # 3. Build command
            try:
                cmd = adapter.build_command(task)
            except Exception as exc:  # noqa: BLE001
                self._fail_task(task, f"Failed to build command: {exc}")
                return self.task_repo.get(task_id) or task

            # 4. Dry-run mode check
            if task.args.get("dry_run"):
                self.audit.log(
                    event_type=AuditEventType.TASK_DRY_RUN,
                    entity_type="task",
                    entity_id=task_id,
                    payload={"command_line": cmd},
                )
                assert_transition(task.status, TaskStatus.SKIPPED)
                now = self.clock.now()
                self.task_repo.update_status(
                    task_id,
                    TaskStatus.SKIPPED,
                    finished_at=now,
                    error_message="Skipped in dry-run mode.",
                )
                return self.task_repo.get(task_id) or task

            # 5. Transition to RUNNING
            now = self.clock.now()
            assert_transition(task.status, TaskStatus.RUNNING)
            self.task_repo.update_status(task_id, TaskStatus.RUNNING, started_at=now)
            self.audit.log(
                event_type=AuditEventType.TASK_STARTED,
                entity_type="task",
                entity_id=task_id,
                payload={"command_line": cmd},
            )
            self.events.publish(
                TaskStarted(
                    task_id=task_id,
                    engagement_id=task.engagement_id,
                    command_line=cmd,
                )
            )

            # 6. Prepare RunContext & run
            ws_dir = self.workspace_provider.get_workspace_dir(task.engagement_id)
            art_dir = self.workspace_provider.get_artifacts_dir(task.engagement_id)

            def _emit_output(line: str) -> None:
                self.events.publish(
                    TaskOutput(
                        task_id=task.id,
                        engagement_id=task.engagement_id,
                        line=line,
                    )
                )

            cancel_event = asyncio.Event()
            self._active_cancels[task_id] = cancel_event

            ctx = RunContext(
                workspace_dir=ws_dir,
                artifacts_dir=art_dir,
                clock=self.clock,
                emit_output=_emit_output,
                timeout_seconds=float(self.cfg.default_timeout_seconds),
                cancel_event=cancel_event,
            )

            try:
                raw_result = await adapter.run(task, ctx)
            except Exception as exc:  # noqa: BLE001
                self._fail_task(task, f"Adapter unhandled exception: {exc}")
                return self.task_repo.get(task_id) or task
            finally:
                self._active_cancels.pop(task_id, None)

            # 7. Check execution outcome
            finished_time = self.clock.now()

            if raw_result.timed_out:
                self._fail_task(
                    task,
                    f"Task execution timed out after {self.cfg.default_timeout_seconds}s.",
                    exit_code=-1,
                )
                return self.task_repo.get(task_id) or task

            if raw_result.exit_code != 0:
                err_str = raw_result.stderr.decode("utf-8", errors="replace")
                self._fail_task(
                    task,
                    f"Adapter exited with code {raw_result.exit_code}: {err_str}",
                    exit_code=raw_result.exit_code,
                )
                return self.task_repo.get(task_id) or task

            # 8. Store and validate artifacts
            for art in raw_result.artifacts:
                art_full_path = (ws_dir / art.path).resolve()
                ws_resolved = ws_dir.resolve()
                if ws_resolved not in art_full_path.parents and art_full_path != ws_resolved:
                    self._fail_task(
                        task,
                        f"Security violation: artifact path {art.path} escapes workspace.",
                    )
                    return self.task_repo.get(task_id) or task

                self.artifact_repo.save(art)

            # 9. Extract and persist observations
            try:
                observations = adapter.parse(raw_result)
                if observations:
                    self.obs_repo.save_many(observations)
            except Exception as exc:  # noqa: BLE001
                self._fail_task(task, f"Failed to parse observations: {exc}")
                return self.task_repo.get(task_id) or task

            # 10. Mark SUCCEEDED
            assert_transition(TaskStatus.RUNNING, TaskStatus.SUCCEEDED)
            self.task_repo.update_status(
                task_id,
                TaskStatus.SUCCEEDED,
                exit_code=raw_result.exit_code,
                finished_at=finished_time,
            )
            self.audit.log(
                event_type=AuditEventType.TASK_SUCCEEDED,
                entity_type="task",
                entity_id=task_id,
                payload={
                    "artifacts_count": len(raw_result.artifacts),
                    "observations_count": len(observations),
                },
            )
            self.events.publish(
                TaskSucceeded(
                    task_id=task_id,
                    engagement_id=task.engagement_id,
                    exit_code=raw_result.exit_code,
                    artifacts_count=len(raw_result.artifacts),
                    observations_count=len(observations),
                )
            )

            return self.task_repo.get(task_id) or task

    def _fail_task(
        self,
        task: Task,
        error_msg: str,
        exit_code: int | None = 1,
    ) -> None:
        now = self.clock.now()
        current_record = self.task_repo.get(task.id)
        current_status = current_record.status if current_record else task.status

        if current_status == TaskStatus.PENDING:
            self.task_repo.update_status(task.id, TaskStatus.RUNNING, started_at=now)
            current_status = TaskStatus.RUNNING

        if can_transition(current_status, TaskStatus.FAILED):
            self.task_repo.update_status(
                task.id,
                TaskStatus.FAILED,
                exit_code=exit_code,
                error_message=error_msg,
                finished_at=now,
            )
            self.audit.log(
                event_type=AuditEventType.TASK_FAILED,
                entity_type="task",
                entity_id=task.id,
                payload={"error": error_msg, "exit_code": exit_code},
            )
            self.events.publish(
                TaskFailed(
                    task_id=task.id,
                    engagement_id=task.engagement_id,
                    error_message=error_msg,
                )
            )

    async def run_all_pending(self, engagement_id: str) -> list[Task]:
        """Sequentially execute all pending tasks for an engagement."""
        pending = self.task_repo.list_by_engagement(engagement_id, TaskStatus.PENDING)
        completed: list[Task] = []
        for t in pending:
            res = await self.execute_task(t.id)
            completed.append(res)
        return completed

    def shutdown(self) -> None:
        """Signal graceful shutdown."""
        self._shutdown_event.set()
        for cancel in self._active_cancels.values():
            cancel.set()
