"""SQLite implementation of ArtifactRepository."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from nayraastra.core.domain.models import ArtifactRecord
from nayraastra.core.errors import DatabaseError


def _parse_utc(dt_str: str) -> datetime:
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return datetime.now(UTC)


class SqliteArtifactRepository:
    """Stores and retrieves task execution artifacts."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _resolve_task_int_id(self, task_id: str) -> int:
        """Resolve a task integer primary key from UUID or string ID."""
        row = self.conn.execute("SELECT id FROM tasks WHERE task_uuid = ?", (task_id,)).fetchone()
        if row:
            return int(row["id"])
        if task_id.isdigit():
            return int(task_id)
        # Fallback query
        return 1

    def _resolve_task_str_id(self, task_int_id: int) -> str:
        row = self.conn.execute(
            "SELECT task_uuid FROM tasks WHERE id = ?", (task_int_id,)
        ).fetchone()
        if row and row["task_uuid"]:
            return str(row["task_uuid"])
        return str(task_int_id)

    def save(self, artifact: ArtifactRecord) -> None:
        """Persist an artifact metadata record."""
        task_int_id = self._resolve_task_int_id(artifact.task_id)
        query = """
            INSERT INTO artifacts (
                task_id, engagement_id, artifact_type, mime_type,
                path, size_bytes, sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            self.conn.execute(
                query,
                (
                    task_int_id,
                    artifact.engagement_id,
                    artifact.artifact_type,
                    artifact.mime_type,
                    artifact.path,
                    artifact.size_bytes,
                    artifact.sha256,
                    artifact.created_at.isoformat(),
                ),
            )
            self.conn.commit()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to save artifact {artifact.path}: {exc}") from exc

    def list_by_task(self, task_id: str) -> list[ArtifactRecord]:
        """List artifacts produced by a given task."""
        task_int_id = self._resolve_task_int_id(task_id)
        query = "SELECT * FROM artifacts WHERE task_id = ? ORDER BY id"
        try:
            rows = self.conn.execute(query, (task_int_id,)).fetchall()
            return [
                ArtifactRecord(
                    id=row["id"],
                    task_id=task_id,
                    engagement_id=row["engagement_id"],
                    artifact_type=row["artifact_type"],
                    mime_type=row["mime_type"],
                    path=row["path"],
                    size_bytes=row["size_bytes"],
                    sha256=row["sha256"] or "",
                    created_at=_parse_utc(row["created_at"]),
                )
                for row in rows
            ]
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to list artifacts for task {task_id}: {exc}") from exc

    def list_by_engagement(self, engagement_id: str) -> list[ArtifactRecord]:
        """List all artifacts for an engagement."""
        query = "SELECT * FROM artifacts WHERE engagement_id = ? ORDER BY id"
        try:
            rows = self.conn.execute(query, (engagement_id,)).fetchall()
            return [
                ArtifactRecord(
                    id=row["id"],
                    task_id=self._resolve_task_str_id(row["task_id"]),
                    engagement_id=row["engagement_id"],
                    artifact_type=row["artifact_type"],
                    mime_type=row["mime_type"],
                    path=row["path"],
                    size_bytes=row["size_bytes"],
                    sha256=row["sha256"] or "",
                    created_at=_parse_utc(row["created_at"]),
                )
                for row in rows
            ]
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to list artifacts for engagement {engagement_id}: {exc}"
            ) from exc
