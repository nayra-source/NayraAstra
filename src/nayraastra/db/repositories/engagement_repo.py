"""SQLite implementation of EngagementRepository."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from nayraastra.core.domain.models import Engagement, RulesOfEngagement
from nayraastra.core.errors import DatabaseError


def _parse_utc(dt_str: str) -> datetime:
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return datetime.now(UTC)


class SqliteEngagementRepository:
    """Stores and retrieves engagement records using plain SQLite3."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save(self, engagement: Engagement) -> None:
        """Create or update an engagement record."""
        roe_json = json.dumps(engagement.roe.model_dump(mode="json"))
        query = """
            INSERT INTO engagements (
                id, name, client, auth_reference, description, status, roe, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                client=excluded.client,
                auth_reference=excluded.auth_reference,
                description=excluded.description,
                status=excluded.status,
                roe=excluded.roe,
                updated_at=excluded.updated_at
        """
        try:
            self.conn.execute(
                query,
                (
                    engagement.id,
                    engagement.name,
                    engagement.client,
                    engagement.auth_reference,
                    engagement.description,
                    engagement.status,
                    roe_json,
                    engagement.created_at.isoformat(),
                    engagement.updated_at.isoformat(),
                ),
            )
            self.conn.commit()
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to save engagement {engagement.id}: {exc}",
                details={"engagement_id": engagement.id},
            ) from exc

    def get(self, engagement_id: str) -> Engagement | None:
        """Retrieve an engagement by ID."""
        query = "SELECT * FROM engagements WHERE id = ?"
        try:
            row = self.conn.execute(query, (engagement_id,)).fetchone()
            if not row:
                return None

            keys = row.keys()
            roe_data = json.loads(row["roe"]) if "roe" in keys and row["roe"] else {}
            roe = RulesOfEngagement.model_validate(roe_data)

            return Engagement(
                id=row["id"],
                name=row["name"],
                client=row["client"] if "client" in keys else "",
                auth_reference=row["auth_reference"] if "auth_reference" in keys else "",
                description=row["description"],
                status=row["status"],
                roe=roe,
                created_at=_parse_utc(row["created_at"]),
                updated_at=_parse_utc(row["updated_at"]),
            )
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to query engagement {engagement_id}: {exc}",
                details={"engagement_id": engagement_id},
            ) from exc

    def list_all(self) -> list[Engagement]:
        """List all engagement records."""
        query = "SELECT * FROM engagements ORDER BY created_at DESC"
        try:
            rows = self.conn.execute(query).fetchall()
            results: list[Engagement] = []
            for row in rows:
                keys = row.keys()
                roe_data = json.loads(row["roe"]) if "roe" in keys and row["roe"] else {}
                roe = RulesOfEngagement.model_validate(roe_data)
                results.append(
                    Engagement(
                        id=row["id"],
                        name=row["name"],
                        client=row["client"] if "client" in keys else "",
                        auth_reference=row["auth_reference"] if "auth_reference" in keys else "",
                        description=row["description"],
                        status=row["status"],
                        roe=roe,
                        created_at=_parse_utc(row["created_at"]),
                        updated_at=_parse_utc(row["updated_at"]),
                    )
                )
            return results
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to list engagements: {exc}") from exc

    def update_status(self, engagement_id: str, status: str, updated_at: datetime) -> None:
        query = "UPDATE engagements SET status = ?, updated_at = ? WHERE id = ?"
        try:
            self.conn.execute(query, (status, updated_at.isoformat(), engagement_id))
            self.conn.commit()
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to update engagement status for {engagement_id}: {exc}"
            ) from exc

    def update_roe(self, engagement_id: str, roe: RulesOfEngagement, updated_at: datetime) -> None:
        roe_json = json.dumps(roe.model_dump(mode="json"))
        query = "UPDATE engagements SET roe = ?, updated_at = ? WHERE id = ?"
        try:
            self.conn.execute(query, (roe_json, updated_at.isoformat(), engagement_id))
            self.conn.commit()
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to update engagement ROE for {engagement_id}: {exc}"
            ) from exc
