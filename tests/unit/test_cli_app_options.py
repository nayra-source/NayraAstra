"""Unit tests for CLI commands, flags, non-TTY detection, and rendering modes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from nayraastra.cli import main
from nayraastra.cli.app import App
from nayraastra.cli.input import PromptToolkitInputDriver
from nayraastra.cli.rendering import create_console
from nayraastra.runtime import build_runtime


@pytest.mark.unit
class TestCliCommandsAndOptions:
    def test_version_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "0.0.1" in captured.out and "nayraastra" in captured.out.lower()

    def test_doctor_command(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["--home", str(tmp_path), "doctor"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "System Doctor" in captured.out
        assert "Python version" in captured.out

    def test_init_db_command(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["--home", str(tmp_path), "init-db"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Database initialised and migrated" in captured.out

    def test_non_tty_stdin_rejected(self, tmp_path: Path) -> None:
        rt = build_runtime(home=tmp_path, dev=True)
        try:
            # When driver is real PromptToolkitInputDriver and sys.stdin.isatty() is False
            app = App(runtime=rt, driver=PromptToolkitInputDriver())
            with patch("sys.stdin.isatty", return_value=False):
                code = app.run()
                assert code == 1
        finally:
            rt.close()

    def test_plain_and_no_color_consoles(self) -> None:
        console_plain = create_console(plain=True)
        assert console_plain.no_color is True

        console_no_color = create_console(no_color=True)
        assert console_no_color.no_color is True
