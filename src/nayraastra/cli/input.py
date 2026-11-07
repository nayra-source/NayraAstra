"""InputDriver abstraction over Prompt Toolkit and scriptable driver for testing."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings

from nayraastra.cli.keybindings import KEY_BACK_ESC, KEY_BACK_ZERO, KEY_CANCEL, KEY_HELP, KEY_SEARCH


class InputCancelledError(Exception):
    """Raised when the user cancels an input prompt via Ctrl+C or Escape."""


class InputDriver(Protocol):
    """Protocol for capturing keyboard inputs, menu choices, and user prompts."""

    async def prompt_menu_choice(
        self,
        item_count: int,
        *,
        bottom_toolbar: str | None = None,
    ) -> str:
        """Read a menu choice.

        If item_count <= 9, accepts single digit instantly.
        If item_count > 9, requires typing the number and pressing Enter.
        Also accepts global keys: '0', Esc, '?', '/', 'q'.
        """
        ...

    async def prompt_text(
        self,
        message: str,
        *,
        default: str = "",
        validator: Callable[[str], bool | str] | None = None,
        bottom_toolbar: str | None = None,
    ) -> str:
        """Prompt user for a line of text with validation and optional cancel ('0')."""
        ...

    async def confirm(
        self,
        message: str,
        *,
        default: bool = False,
        bottom_toolbar: str | None = None,
    ) -> bool:
        """Prompt user with a yes/no confirmation prompt [y/N] or [Y/n]."""
        ...

    async def confirm_phrase(
        self,
        message: str,
        expected_phrase: str,
        *,
        bottom_toolbar: str | None = None,
    ) -> bool:
        """Require typing an exact phrase (e.g. engagement name for disruptive opt-in)."""
        ...


# ---------------------------------------------------------------------------
# Prompt Toolkit Implementation
# ---------------------------------------------------------------------------


class PromptToolkitInputDriver:
    """Production input driver powered by prompt_toolkit."""

    def __init__(self, session: PromptSession[str] | None = None) -> None:
        self.session = session or PromptSession[str]()

    async def prompt_menu_choice(
        self,
        item_count: int,
        *,
        bottom_toolbar: str | None = None,
    ) -> str:
        kb = KeyBindings()
        result_container: list[str] = []

        # If <= 9 items, single keypress instantly returns
        if item_count <= 9:
            valid_digits = [str(i) for i in range(1, item_count + 1)]

            for digit in valid_digits:

                @kb.add(digit)
                def _digit(event: object, d: str = digit) -> None:
                    result_container.append(d)
                    app = getattr(event, "app", None)
                    if app:
                        app.exit(result=d)

        @kb.add("0")
        def _zero(event: object) -> None:
            result_container.append(KEY_BACK_ZERO)
            app = getattr(event, "app", None)
            if app:
                app.exit(result=KEY_BACK_ZERO)

        @kb.add("escape")
        def _esc(event: object) -> None:
            result_container.append(KEY_BACK_ESC)
            app = getattr(event, "app", None)
            if app:
                app.exit(result=KEY_BACK_ESC)

        @kb.add("?")
        def _help(event: object) -> None:
            result_container.append(KEY_HELP)
            app = getattr(event, "app", None)
            if app:
                app.exit(result=KEY_HELP)

        @kb.add("/")
        def _search(event: object) -> None:
            result_container.append(KEY_SEARCH)
            app = getattr(event, "app", None)
            if app:
                app.exit(result=KEY_SEARCH)

        @kb.add("q")
        def _quit(event: object) -> None:
            result_container.append("q")
            app = getattr(event, "app", None)
            if app:
                app.exit(result="q")

        def _toolbar() -> HTML:
            return HTML(f"<style bg='ansiblue' fg='ansiwhite'>{bottom_toolbar or ''}</style>")

        try:
            val = await self.session.prompt_async(
                HTML("<ansicyan><b>Select: </b></ansicyan>"),
                key_bindings=kb,
                bottom_toolbar=_toolbar if bottom_toolbar else None,
            )
            return val.strip()
        except KeyboardInterrupt:
            return KEY_CANCEL

    async def prompt_text(
        self,
        message: str,
        *,
        default: str = "",
        validator: Callable[[str], bool | str] | None = None,
        bottom_toolbar: str | None = None,
    ) -> str:
        def _toolbar() -> HTML:
            return HTML(f"<style bg='ansiblue' fg='ansiwhite'>{bottom_toolbar or ''}</style>")

        while True:
            try:
                val = await self.session.prompt_async(
                    HTML(f"<ansicyan>{message}</ansicyan> "),
                    default=default,
                    bottom_toolbar=_toolbar if bottom_toolbar else None,
                )
                stripped = val.strip()
                if validator is not None:
                    res = validator(stripped)
                    if res is True:
                        return stripped
                    if isinstance(res, str):
                        print(f"\n[!] {res}\n")
                        continue
                    print("\n[!] Invalid input\n")
                    continue
                return stripped
            except KeyboardInterrupt:
                return KEY_CANCEL

    async def confirm(
        self,
        message: str,
        *,
        default: bool = False,
        bottom_toolbar: str | None = None,
    ) -> bool:
        hint = "[Y/n]" if default else "[y/N]"
        res = await self.prompt_text(
            f"{message} {hint}:",
            default="y" if default else "n",
            bottom_toolbar=bottom_toolbar,
        )
        if res == KEY_CANCEL:
            return False
        cleaned = res.strip().lower()
        if not cleaned:
            return default
        return cleaned in ("y", "yes")

    async def confirm_phrase(
        self,
        message: str,
        expected_phrase: str,
        *,
        bottom_toolbar: str | None = None,
    ) -> bool:
        res = await self.prompt_text(
            message,
            bottom_toolbar=bottom_toolbar,
        )
        return res == expected_phrase


# ---------------------------------------------------------------------------
# Scripted / Mock Implementation for Tests
# ---------------------------------------------------------------------------


class ScriptedInputDriver:
    """Deterministic scriptable input driver for automated and unit testing."""

    def __init__(self, inputs: Sequence[str | bool] | None = None) -> None:
        self.inputs: list[str | bool] = list(inputs or [])
        self.history: list[str | bool] = []

    def feed(self, *items: str | bool) -> None:
        """Append scripted inputs to the queue."""
        self.inputs.extend(items)

    async def prompt_menu_choice(
        self,
        item_count: int,
        *,
        bottom_toolbar: str | None = None,
    ) -> str:
        if not self.inputs:
            return KEY_BACK_ZERO
        val = str(self.inputs.pop(0))
        self.history.append(val)
        return val

    async def prompt_text(
        self,
        message: str,
        *,
        default: str = "",
        validator: Callable[[str], bool | str] | None = None,
        bottom_toolbar: str | None = None,
    ) -> str:
        if not self.inputs:
            return default or KEY_CANCEL
        val = str(self.inputs.pop(0))
        self.history.append(val)
        if validator:
            res = validator(val)
            if res is not True and isinstance(res, str) and self.inputs:
                # Invalid input, if more inputs exist, retry next input
                return await self.prompt_text(
                    message,
                    default=default,
                    validator=validator,
                    bottom_toolbar=bottom_toolbar,
                )
        return val

    async def confirm(
        self,
        message: str,
        *,
        default: bool = False,
        bottom_toolbar: str | None = None,
    ) -> bool:
        if not self.inputs:
            return default
        val = self.inputs.pop(0)
        self.history.append(val)
        if isinstance(val, bool):
            return val
        s = str(val).strip().lower()
        if not s:
            return default
        return s in ("y", "yes", "true", "1")

    async def confirm_phrase(
        self,
        message: str,
        expected_phrase: str,
        *,
        bottom_toolbar: str | None = None,
    ) -> bool:
        if not self.inputs:
            return False
        val = self.inputs.pop(0)
        self.history.append(val)
        return str(val) == expected_phrase
