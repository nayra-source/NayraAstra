"""Task creation, authorization, and persistence service."""

from __future__ import annotations

from typing import Any

from nayraastra.core.audit.logger import AuditLogger
from nayraastra.core.audit.models import AuditEventType
from nayraastra.core.domain.models import Engagement, Target, Task
from nayraastra.core.domain.time_id import Clock, IdGenerator
from nayraastra.core.domain.types import Capability, TaskStatus
from nayraastra.core.errors import ValidationFailure
from nayraastra.core.events.bus import EventBus
from nayraastra.core.events.models import (
    ScopeViolation,
    TaskBlocked,
    TaskQueued,
)
from nayraastra.core.ports import AdapterRegistryPort, ScopeRepository, TaskRepository
from nayraastra.core.scope.authorizer import TaskAuthorizer
from nayraastra.core.scope.guard import ScopeGuard
from nayraastra.core.scope.normalize import normalize_target


class TaskService:
    """Manages task lifecycle from submission to authorization and scheduling."""

    def __init__(
        self,
        task_repo: TaskRepository,
        scope_repo: ScopeRepository,
        registry: AdapterRegistryPort,
        authorizer: TaskAuthorizer,
        audit: AuditLogger,
        events: EventBus,
        clock: Clock,
        id_gen: IdGenerator,
    ) -> None:
        self.task_repo = task_repo
        self.scope_repo = scope_repo
        self.registry = registry
        self.authorizer = authorizer
        self.audit = audit
        self.events = events
        self.clock = clock
        self.id_gen = id_gen

    def queue(
        self,
        engagement: Engagement,
        capability: Capability,
        target: str | Target,
        params: dict[str, Any] | None = None,
        profile: str | None = None,
        adapter_name: str | None = None,
    ) -> Task:
        """Authorize and queue a task for execution."""
        # Normalize target
        norm_target: Target
        norm_target = normalize_target(target) if isinstance(target, str) else target

        # Select adapter
        adapter = None
        if adapter_name:
            adapter = self.registry.get(adapter_name)
            if not adapter:
                raise ValidationFailure(
                    f"Requested adapter {adapter_name!r} not found in registry."
                )
        else:
            candidates = self.registry.for_capability(capability)
            if not candidates:
                raise ValidationFailure(
                    f"No registered adapter provides capability {capability.value!r}."
                )
            adapter = candidates[0]

        intrusiveness = adapter.intrusiveness
        task_args = dict(params or {})
        if profile:
            task_args["profile"] = profile

        # Load scope entries for this engagement
        scope_entries = self.scope_repo.list_entries(engagement.id)
        guard = ScopeGuard(scope_entries)

        # Run authorizer gate
        decision = self.authorizer.authorize(
            engagement=engagement,
            scope_guard=guard,
            target=norm_target,
            capability=capability,
            intrusiveness=intrusiveness,
        )

        task_id = self.id_gen.generate()
        now = self.clock.now()

        if not decision.allowed:
            # Task is blocked: persist, audit, emit, NEVER dispatch to adapter
            task = Task(
                id=task_id,
                engagement_id=engagement.id,
                module_name=capability.value,
                adapter_name=adapter.name,
                capability=capability,
                target=norm_target,
                status=TaskStatus.BLOCKED,
                intrusiveness=intrusiveness,
                args=task_args,
                error_message="; ".join(decision.violations),
                created_at=now,
            )
            self.task_repo.save(task)

            self.audit.log(
                event_type=AuditEventType.POLICY_DENIED,
                entity_type="task",
                entity_id=task_id,
                payload={
                    "target": norm_target.normalized,
                    "capability": capability.value,
                    "adapter": adapter.name,
                    "violations": decision.violations,
                },
            )

            self.audit.log(
                event_type=AuditEventType.TASK_BLOCKED,
                entity_type="task",
                entity_id=task_id,
                payload={"reason": task.error_message},
            )

            self.events.publish(
                ScopeViolation(
                    engagement_id=engagement.id,
                    target=norm_target.normalized,
                    violations=decision.violations,
                )
            )

            self.events.publish(
                TaskBlocked(
                    task_id=task_id,
                    engagement_id=engagement.id,
                    reason=task.error_message or "Blocked by policy",
                )
            )

            return task

        # Task is authorized: persist as PENDING
        task = Task(
            id=task_id,
            engagement_id=engagement.id,
            module_name=capability.value,
            adapter_name=adapter.name,
            capability=capability,
            target=norm_target,
            status=TaskStatus.PENDING,
            intrusiveness=intrusiveness,
            args=task_args,
            created_at=now,
        )
        self.task_repo.save(task)

        self.audit.log(
            event_type=AuditEventType.TASK_QUEUED,
            entity_type="task",
            entity_id=task_id,
            payload={
                "target": norm_target.normalized,
                "capability": capability.value,
                "adapter": adapter.name,
                "intrusiveness": intrusiveness.value,
            },
        )

        self.events.publish(
            TaskQueued(
                task_id=task_id,
                engagement_id=engagement.id,
                module_name=capability.value,
                adapter_name=adapter.name,
                target=norm_target.normalized,
            )
        )

        return task

    def get(self, task_id: str) -> Task | None:
        """Retrieve task by ID."""
        return self.task_repo.get(task_id)

    def list_by_engagement(
        self, engagement_id: str, status: TaskStatus | None = None
    ) -> list[Task]:
        """List tasks for an engagement."""
        return self.task_repo.list_by_engagement(engagement_id, status)
