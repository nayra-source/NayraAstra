"""Theme and semantic styles for the NAYRAASTRA CLI."""

from __future__ import annotations

from rich.theme import Theme

# Semantic color definitions
STYLE_SUCCESS = "bold green"
STYLE_WARNING = "bold yellow"
STYLE_DANGER = "bold red"
STYLE_MUTED = "dim"
STYLE_ACCENT = "bold cyan"
STYLE_LOCKED = "dim yellow"
STYLE_INFO = "cyan"
STYLE_HEADER = "bold white on dark_blue"
STYLE_KEY = "bold cyan"
STYLE_VAL = "white"

CLI_THEME = Theme(
    {
        "success": STYLE_SUCCESS,
        "warning": STYLE_WARNING,
        "danger": STYLE_DANGER,
        "muted": STYLE_MUTED,
        "accent": STYLE_ACCENT,
        "locked": STYLE_LOCKED,
        "info": STYLE_INFO,
        "header": STYLE_HEADER,
        "key": STYLE_KEY,
        "val": STYLE_VAL,
    }
)
