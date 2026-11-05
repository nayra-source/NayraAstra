"""SQLite implementation of TaskRepository."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from nayraastra.core.domain.models import Target, Task
from nayraastra.core.domain.types import Capability, Intrusiveness, TargetKind, TaskStatus
from nayraastra.core.errors import DatabaseError


def _parse_utc(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


def _row_to_task(row: sqlite3.Row) -> Task:
    args_data = json.loads(row["args"]) if row["args"] else {}
    target_data = args_data.get("target")

    if target_data and isinstance(target_data, dict):
        target = Target.model_validate(target_data)
    else:
        # Fallback target reconstruction
        target_val = args_data.get("target_val", "unknown")
        target = Target(raw=target_val, normalized=target_val, kind=TargetKind.IP)

    capability_str = args_data.get("capability", row["module_name"])
    try:
        cap = Capability(capability_str)
    except ValueError:
        cap = Capability.PORT_SCAN

    # Use task_uuid if available, else string of row id
    task_id = row["task_uuid"] if "task_uuid" in row.keys() and row["task_uuid"] else str(row["id"])

    created_at = _parse_utc(row["created_at"]) or datetime.now(UTC)

    return Task(
        id=task_id,
        engagement_id=row["engagement_id"],
        workflow_run_id=row["workflow_run_id"],
        module_name=row["module_name"],
        adapter_name=row["adapter_name"],
        capability=cap,
        target=target,
        status=TaskStatus(row["status"]),
        intrusiveness=Intrusiveness(row["intrusiveness"]),
        args=args_data,
        started_at=_parse_utc(row["started_at"]),
        finished_at=_parse_utc(row["finished_at"]),
        exit_code=row["exit_code"],
        error_message=row["error_message"],
        created_at=created_at,
    )


class SqliteTaskRepository:
    """Stores and retrieves task records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save(self, task: Task) -> None:
        """Create or update a task record."""
        # Pack target and capability inside args JSON for lossless round-tripping
        packed_args = dict(task.args)
        packed_args["target"] = task.target.model_dump(mode="json")
        packed_args["capability"] = task.capability.value
        args_json = json.dumps(packed_args)

        query = """
            INSERT INTO tasks (
                engagement_id, workflow_run_id, module_name, adapter_name,
                status, intrusiveness, args, started_at, finished_at,
                exit_code, error_message, created_at, task_uuid
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_uuid) DO UPDATE SET
                status=excluded.status,
                started_at=excluded.started_at,
                finished_at=excluded.finished_at,
                exit_code=excluded.exit_code,
                error_message=excluded.error_message,
                args=excluded.args
        """
        try:
            self.conn.execute(
                query,
                (
                    task.engagement_id,
                    task.workflow_run_id,
                    task.module_name,
                    task.adapter_name,
                    task.status.value,
                    task.intrusiveness.value,
                    args_json,
                    task.started_at.isoformat() if task.started_at else None,
                    task.finished_at.isoformat() if task.finished_at else None,
                    task.exit_code,
                    task.error_message,
                    task.created_at.isoformat(),
                    task.id,
                ),
            )
            self.conn.commit()
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to save task {task.id}: {exc}", details={"task_id": task.id}
            ) from exc

    def get(self, task_id: str) -> Task | None:
        """Find a task by task_uuid or integer id."""
        try:
            # First try task_uuid
            row = self.conn.execute(
                "SELECT * FROM tasks WHERE task_uuid = ?", (task_id,)
            ).fetchone()
            if not row and task_id.isdigit():
                row = self.conn.execute(
                    "SELECT * FROM tasks WHERE id = ?", (int(task_id),)
                ).fetchone()

            if not row:
                return None
            return _row_to_task(row)
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to query task {task_id}: {exc}", details={"task_id": task_id}
            ) from exc

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        exit_code: int | None = None,
        error_message: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        """Update task status and timing in database."""
        query = """
            UPDATE tasks SET
                status = ?,
                exit_code = COALESCE(?, exit_code),
                error_message = COALESCE(?, error_message),
                started_at = COALESCE(?, started_at),
                finished_at = COALESCE(?, finished_at)
            WHERE task_uuid = ? OR (id = ? AND task_uuid IS NULL)
        """
        try:
            int_id = int(task_id) if task_id.isdigit() else -1
            self.conn.execute(
                query,
                (
                    status.value,
                    exit_code,
                    error_message,
                    started_at.isoformat() if started_at else None,
                    finished_at.isoformat() if finished_at else None,
                    task_id,
                    int_id,
                ),
            )
            self.conn.commit()
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to update status for task {task_id}: {exc}",
                details={"task_id": task_id},
            ) from exc

    def list_by_engagement(
        self, engagement_id: str, status: TaskStatus | None = None
    ) -> list[Task]:
        """List tasks belonging to an engagement."""
        try:
            if status:
                rows = self.conn.execute(
                    "SELECT * FROM tasks WHERE engagement_id = ? AND status = ? ORDER BY id",
                    (engagement_id, status.value),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM tasks WHERE engagement_id = ? ORDER BY id",
                    (engagement_id,),
                ).fetchall()

            return [_row_to_task(r) for r in rows]
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to list tasks for engagement {engagement_id}: {exc}"
            ) from exc

    def find_interrupted(self) -> list[Task]:
        """List tasks currently marked RUNNING."""
        try:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE status = 'running' ORDER BY id"
            ).fetchall()
            return [_row_to_task(r) for r in rows]
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to find interrupted tasks: {exc}") from exc
