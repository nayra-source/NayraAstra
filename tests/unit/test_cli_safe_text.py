"""Unit tests for untrusted text sanitization and injection prevention."""

from __future__ import annotations

import pytest
from rich.console import Console

from nayraastra.cli.rendering import safe_text


@pytest.mark.unit
class TestSafeTextSanitization:
    def test_strips_ansi_color_codes(self) -> None:
        malicious = "\x1b[31mRed Alert\x1b[0m"
        clean = safe_text(malicious)
        assert "\x1b" not in clean
        assert "Red Alert" in clean

    def test_escapes_rich_markup_tags(self) -> None:
        malicious = "[bold red]System Compromised[/bold red]"
        clean = safe_text(malicious)
        assert clean == r"\[bold red]System Compromised\[/bold red]"

        # Ensure Rich console renders it literally without styling
        console = Console(record=True, color_system=None)
        console.print(clean)
        rendered = console.export_text()
        assert "[bold red]" in rendered

    def test_removes_nul_bytes(self) -> None:
        malicious = "target.local\x00malicious.com"
        clean = safe_text(malicious)
        assert "\x00" not in clean
        assert clean == "target.localmalicious.com"

    def test_removes_bidi_override_characters(self) -> None:
        # Bidi right-to-left override \u202e
        malicious = "user\u202e\u202dadmin"
        clean = safe_text(malicious)
        assert "\u202e" not in clean
        assert "\u202d" not in clean
        assert clean == "useradmin"

    def test_handles_control_characters(self) -> None:
        # Bel \x07, Backspace \x08, Formfeed \x0c
        malicious = "scan\x07target\x08host\x0c"
        clean = safe_text(malicious)
        assert clean == "scantargethost"

    def test_allow_newlines_toggle(self) -> None:
        multiline = "line1\nline2\r\nline3"
        clean_no_newlines = safe_text(multiline, allow_newlines=False)
        assert "\n" not in clean_no_newlines

        clean_with_newlines = safe_text(multiline, allow_newlines=True)
        assert clean_with_newlines == "line1\nline2\nline3"

    def test_handles_none_and_non_string_types(self) -> None:
        assert safe_text(None) == ""
        assert safe_text(12345) == "12345"
        assert safe_text(["a", "b"]) == r"['a', 'b']"

    def test_handles_very_long_strings(self) -> None:
        long_str = "A" * 10000 + "[red]test[/red]"
        clean = safe_text(long_str)
        assert len(clean) > 10000
        assert r"\[red]test\[/red]" in clean
