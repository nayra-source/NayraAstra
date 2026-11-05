"""Unit tests for the NAYRAASTRA CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import nayraastra
from nayraastra.cli import main


@pytest.mark.unit
class TestVersionFlag:
    def test_version_exit_code(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0

    def test_version_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            main(["--version"])
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert nayraastra.__version__ in combined
        assert "NAYRAASTRA" in combined

    def test_module_invocation_version(self) -> None:
        """python -m nayraastra --version must work and exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "nayraastra", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        combined = result.stdout + result.stderr
        assert nayraastra.__version__ in combined


@pytest.mark.unit
class TestDoctorCommand:
    def test_doctor_exits_zero(self, fake_home: Path) -> None:
        result = main(["doctor"])
        assert result == 0

    def test_no_subcommand_exits_zero(self, fake_home: Path) -> None:
        result = main([])
        assert result == 0


@pytest.mark.unit
class TestInitDb:
    def test_init_db_with_path(self, tmp_path: Path, fake_home: Path) -> None:
        db_path = tmp_path / "test_init.db"
        result = main(["init-db", "--path", str(db_path)])
        assert result == 0
        assert db_path.exists()

    def test_init_db_default_path(self, fake_home: Path) -> None:
        result = main(["init-db"])
        assert result == 0
        # DB should be created in the fake home.
        db_file = fake_home / "nayraastra.db"
        assert db_file.exists()

    def test_init_db_idempotent(self, tmp_path: Path, fake_home: Path) -> None:
        db_path = tmp_path / "idempotent.db"
        assert main(["init-db", "--path", str(db_path)]) == 0
        assert main(["init-db", "--path", str(db_path)]) == 0
