"""Global keybinding definitions and key codes for the NAYRAASTRA CLI."""

from __future__ import annotations

KEY_BACK_ZERO = "0"
KEY_BACK_ESC = "escape"
KEY_HELP = "?"
KEY_SEARCH = "/"
KEY_REDRAW = "c-l"
KEY_CANCEL = "c-c"
KEY_QUIT = "q"
KEY_ENTER = "enter"
KEY_UP = "up"
KEY_DOWN = "down"

GLOBAL_KEY_HINTS = (
    ("[0/Esc]", "Back"),
    ("[?]", "Help"),
    ("[/]", "Filter"),
    ("[Ctrl+L]", "Redraw"),
    ("[Ctrl+C]", "Cancel"),
)

MAIN_MENU_KEY_HINTS = (
    ("[0/q]", "Exit"),
    ("[?]", "Help"),
    ("[/]", "Filter"),
    ("[Ctrl+L]", "Redraw"),
    ("[Ctrl+C]", "Cancel"),
)
