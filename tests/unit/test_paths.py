"""Unit tests for nayraastra.core.paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from nayraastra.core.errors import ValidationFailure
from nayraastra.core.paths import (
    ensure_home,
    get_home,
    get_logs_dir,
    get_workspace_dir,
    get_workspaces_dir,
    validate_engagement_id,
)


@pytest.mark.unit
class TestGetHome:
    def test_default_home_is_under_user_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NAYRAASTRA_HOME", raising=False)
        home = get_home()
        assert home.name == ".nayraastra"

    def test_env_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NAYRAASTRA_HOME", str(tmp_path / "custom"))
        home = get_home()
        assert home == tmp_path / "custom"


@pytest.mark.unit
class TestEnsureHome:
    def test_creates_directory(self, fake_home: Path) -> None:
        # fake_home fixture already sets the env var; ensure_home should use it.
        result = ensure_home()
        assert result.exists()
        assert result.is_dir()

    def test_directory_mode_700(self, fake_home: Path) -> None:
        result = ensure_home()
        mode = result.stat().st_mode & 0o777
        assert mode == 0o700

    def test_idempotent(self, fake_home: Path) -> None:
        ensure_home()
        ensure_home()  # Should not raise.
        assert fake_home.exists()


@pytest.mark.unit
class TestGetLogsDir:
    def test_creates_logs_dir(self, fake_home: Path) -> None:
        logs = get_logs_dir()
        assert logs.exists()
        assert logs.name == "logs"

    def test_logs_inside_home(self, fake_home: Path) -> None:
        logs = get_logs_dir()
        assert logs.parent == fake_home


@pytest.mark.unit
class TestGetWorkspacesDir:
    def test_creates_workspaces_dir(self, fake_home: Path) -> None:
        ws = get_workspaces_dir()
        assert ws.exists()
        assert ws.name == "workspaces"


@pytest.mark.unit
class TestValidateEngagementId:
    @pytest.mark.parametrize(
        "valid_id",
        ["abc", "ENGAGEMENT-001", "test_01", "my.project", "A" * 64, "a-b_c.1"],
    )
    def test_valid_ids_pass(self, valid_id: str) -> None:
        validate_engagement_id(valid_id)  # Must not raise.

    @pytest.mark.parametrize(
        "invalid_id",
        [
            "",            # empty
            "../x",        # path traversal
            "a/b",         # path separator
            "a\\b",        # backslash
            "A" * 65,      # too long
            "hello world", # space
            "test!@#",     # special chars
        ],
    )
    def test_invalid_ids_rejected(self, invalid_id: str) -> None:
        with pytest.raises(ValidationFailure):
            validate_engagement_id(invalid_id)

    def test_error_includes_id(self) -> None:
        with pytest.raises(ValidationFailure) as exc_info:
            validate_engagement_id("bad/id")
        assert "bad/id" in exc_info.value.details.get("engagement_id", "")


@pytest.mark.unit
class TestGetWorkspaceDir:
    def test_creates_workspace(self, fake_home: Path) -> None:
        ws = get_workspace_dir("my-engagement")
        assert ws.exists()
        assert ws.name == "my-engagement"

    def test_creates_subdirs(self, fake_home: Path) -> None:
        ws = get_workspace_dir("test-eng")
        assert (ws / "artifacts").exists()
        assert (ws / "raw").exists()

    def test_workspace_inside_workspaces(self, fake_home: Path) -> None:
        ws = get_workspace_dir("eng-001")
        assert ws.parent.name == "workspaces"

    def test_rejects_path_traversal(self, fake_home: Path) -> None:
        with pytest.raises(ValidationFailure):
            get_workspace_dir("../escape")

    def test_idempotent(self, fake_home: Path) -> None:
        ws1 = get_workspace_dir("repeated")
        ws2 = get_workspace_dir("repeated")
        assert ws1 == ws2

