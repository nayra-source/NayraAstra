"""Form and field input prompts with cancellation and validation support."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from nayraastra.cli.keybindings import KEY_BACK_ZERO, KEY_CANCEL

if TYPE_CHECKING:
    from nayraastra.cli.input import InputDriver


async def prompt_field(
    driver: InputDriver,
    label: str,
    *,
    default: str = "",
    required: bool = True,
    validator: Callable[[str], bool | str] | None = None,
    bottom_toolbar: str | None = None,
) -> str | None:
    """Prompt for a text field. Returns None if cancelled ('0' or Ctrl+C)."""
    msg = f"{label} (0 to cancel):" if not default else f"{label} [{default}] (0 to cancel):"

    def _combined_validator(val: str) -> bool | str:
        if val == KEY_BACK_ZERO:
            return True
        if required and not val and not default:
            return "Value is required."
        if validator:
            return validator(val or default)
        return True

    res = await driver.prompt_text(
        msg,
        default="",
        validator=_combined_validator,
        bottom_toolbar=bottom_toolbar,
    )
    if res in (KEY_BACK_ZERO, KEY_CANCEL):
        return None
    return res or default
