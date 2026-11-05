"""SQLite implementation of ObservationRepository."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from nayraastra.core.domain.models import Observation
from nayraastra.core.errors import DatabaseError


def _parse_utc(dt_str: str) -> datetime:
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return datetime.now(UTC)


class SqliteObservationRepository:
    """Stores and retrieves observations extracted from security tools."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _resolve_task_int_id(self, task_id: str) -> int:
        row = self.conn.execute("SELECT id FROM tasks WHERE task_uuid = ?", (task_id,)).fetchone()
        if row:
            return int(row["id"])
        if task_id.isdigit():
            return int(task_id)
        return 1

    def _resolve_task_str_id(self, task_int_id: int) -> str:
        row = self.conn.execute(
            "SELECT task_uuid FROM tasks WHERE id = ?", (task_int_id,)
        ).fetchone()
        if row and row["task_uuid"]:
            return str(row["task_uuid"])
        return str(task_int_id)

    def save(self, observation: Observation) -> None:
        self.save_many([observation])

    def save_many(self, observations: list[Observation]) -> None:
        """Persist a batch of observations."""
        if not observations:
            return

        query = """
            INSERT INTO observations (
                task_id, engagement_id, host_id, observation_key, value, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """
        params = [
            (
                self._resolve_task_int_id(obs.task_id),
                obs.engagement_id,
                obs.host_id,
                obs.observation_key,
                json.dumps(obs.value),
                obs.observed_at.isoformat(),
            )
            for obs in observations
        ]
        try:
            self.conn.executemany(query, params)
            self.conn.commit()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to persist observations batch: {exc}") from exc

    def list_by_task(self, task_id: str) -> list[Observation]:
        """List observations extracted from a specific task."""
        task_int_id = self._resolve_task_int_id(task_id)
        query = "SELECT * FROM observations WHERE task_id = ? ORDER BY id"
        try:
            rows = self.conn.execute(query, (task_int_id,)).fetchall()
            return [
                Observation(
                    id=row["id"],
                    task_id=task_id,
                    engagement_id=row["engagement_id"],
                    host_id=row["host_id"],
                    observation_key=row["observation_key"],
                    value=json.loads(row["value"]),
                    observed_at=_parse_utc(row["observed_at"]),
                )
                for row in rows
            ]
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to list observations for task {task_id}: {exc}") from exc

    def list_by_engagement(self, engagement_id: str) -> list[Observation]:
        """List all observations for an engagement."""
        query = "SELECT * FROM observations WHERE engagement_id = ? ORDER BY id"
        try:
            rows = self.conn.execute(query, (engagement_id,)).fetchall()
            return [
                Observation(
                    id=row["id"],
                    task_id=self._resolve_task_str_id(row["task_id"]),
                    engagement_id=row["engagement_id"],
                    host_id=row["host_id"],
                    observation_key=row["observation_key"],
                    value=json.loads(row["value"]),
                    observed_at=_parse_utc(row["observed_at"]),
                )
                for row in rows
            ]
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to list observations for engagement {engagement_id}: {exc}"
            ) from exc
