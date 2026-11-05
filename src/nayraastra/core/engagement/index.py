"""Atomic global engagement registry index (<home>/engagements.json)."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from nayraastra.core.errors import ValidationFailure


class IndexEntry(BaseModel, frozen=True, extra="forbid"):
    """Summary record in global index."""

    id: str
    name: str
    client: str = ""
    status: str = "active"
    created_at: str
    updated_at: str


class EngagementIndexDocument(BaseModel, frozen=True, extra="forbid"):
    """Root model for engagements.json."""

    version: int = 1
    engagements: list[IndexEntry] = Field(default_factory=list)


def load_index(home_dir: Path) -> list[IndexEntry]:
    """Read the global index file, returning empty list if missing or corrupted."""
    index_path = home_dir / "engagements.json"
    if not index_path.exists():
        return []

    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        doc = EngagementIndexDocument.model_validate(data)
        return list(doc.engagements)
    except Exception:
        # Tolerant of corruption – callers can re-index or start fresh
        return []


def save_index(home_dir: Path, entries: list[IndexEntry]) -> None:
    """Atomically write the global index file using tempfile + os.replace."""
    home_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    index_path = home_dir / "engagements.json"

    doc = EngagementIndexDocument(version=1, engagements=list(entries))
    content = doc.model_dump_json(indent=2)

    # Write to a temporary file in the same directory to guarantee atomic replace
    fd, tmp_path_str = tempfile.mkstemp(dir=str(home_dir), prefix="engagements_", suffix=".tmp")
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, index_path)
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        raise ValidationFailure(f"Failed to atomically write index: {exc}") from exc


def update_index_entry(
    home_dir: Path,
    *,
    engagement_id: str,
    name: str,
    client: str = "",
    status: str = "active",
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> None:
    """Add or update a single engagement summary in the index."""
    entries = load_index(home_dir)
    now_iso = datetime.now(UTC).isoformat()
    c_iso = created_at.isoformat() if created_at else now_iso
    u_iso = updated_at.isoformat() if updated_at else now_iso

    updated_list: list[IndexEntry] = []
    found = False

    for e in entries:
        if e.id == engagement_id:
            updated_list.append(
                IndexEntry(
                    id=engagement_id,
                    name=name,
                    client=client,
                    status=status,
                    created_at=e.created_at or c_iso,
                    updated_at=u_iso,
                )
            )
            found = True
        else:
            updated_list.append(e)

    if not found:
        updated_list.append(
            IndexEntry(
                id=engagement_id,
                name=name,
                client=client,
                status=status,
                created_at=c_iso,
                updated_at=u_iso,
            )
        )

    save_index(home_dir, updated_list)
