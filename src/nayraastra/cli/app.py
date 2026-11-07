"""Interactive application loop owning Runtime, SessionState, and Navigator."""

from __future__ import annotations

import asyncio
import sys

from rich.console import Console

from nayraastra.cli.input import InputDriver, PromptToolkitInputDriver, ScriptedInputDriver
from nayraastra.cli.keybindings import KEY_BACK_ESC, KEY_BACK_ZERO, KEY_HELP, KEY_REDRAW
from nayraastra.cli.navigation import Exit, Navigator, Pop, Push, Replace, Stay
from nayraastra.cli.rendering import create_console
from nayraastra.cli.screens.help import HelpScreen
from nayraastra.cli.screens.main_menu import MainMenuScreen
from nayraastra.cli.state import SessionState
from nayraastra.cli.widgets.statusbar import build_status_bar_view_model
from nayraastra.runtime import Runtime


class App:
    """Top-level CLI application controller managing screens, input, and lifecycle."""

    def __init__(
        self,
        runtime: Runtime,
        *,
        driver: InputDriver | None = None,
        console: Console | None = None,
        is_dev: bool = False,
        plain: bool = False,
        no_color: bool = False,
    ) -> None:
        self.runtime = runtime
        self.is_dev = is_dev
        self.plain = plain
        self.no_color = no_color
        self.console = console or create_console(plain=plain, no_color=no_color)
        self.driver = driver or PromptToolkitInputDriver()
        self.state = SessionState(is_dev=is_dev, config=self.runtime.config)
        self.navigator = Navigator(MainMenuScreen())

    async def run_async(self) -> int:
        """Run the interactive application event loop."""
        # Non-TTY check: require a TTY for live interactive prompt_toolkit unless running scripted tests
        if not isinstance(self.driver, ScriptedInputDriver) and not sys.stdin.isatty():
            self.console.print(
                "[bold red]Error:[/bold red] Interactive shell requires a TTY terminal.\n"
                "Standard input is not a terminal."
            )
            return 1

        running = True
        while running:
            current_screen = self.navigator.current
            self.console.print()
            current_screen.render(self.state, self.console)

            # Generate status bar for Prompt Toolkit bottom toolbar
            sb_vm = build_status_bar_view_model(self.state)
            toolbar_str = sb_vm.to_toolbar_string()

            # Read menu choice or input
            try:
                user_input = await self.driver.prompt_menu_choice(
                    item_count=9,
                    bottom_toolbar=toolbar_str,
                )
            except (KeyboardInterrupt, asyncio.CancelledError):
                continue

            cleaned = user_input.strip()

            # Global screen controls
            if cleaned == KEY_REDRAW:
                continue

            if cleaned == KEY_HELP and not isinstance(current_screen, HelpScreen):
                self.navigator.push(HelpScreen())
                continue

            if cleaned in (KEY_BACK_ZERO, KEY_BACK_ESC):
                if self.navigator.is_root:
                    # At main menu, '0' delegates to screen handle for exit confirmation
                    pass
                else:
                    self.navigator.pop()
                    continue

            # Dispatch to screen
            try:
                action = await current_screen.handle(
                    cleaned,
                    self.state,
                    self.driver,
                    self.runtime,
                )
            except Exception as exc:  # noqa: BLE001
                self.console.print(f"[bold red]Error in screen handler:[/bold red] {exc}")
                continue

            if isinstance(action, Push):
                self.navigator.push(action.screen)
            elif isinstance(action, Pop):
                if not self.navigator.is_root:
                    self.navigator.pop()
            elif isinstance(action, Replace):
                self.navigator.replace(action.screen)
            elif isinstance(action, Exit):
                running = False
            elif isinstance(action, Stay):
                pass

        # Cleanup on exit
        self.runtime.close()
        return 0

    def run(self) -> int:
        """Synchronous entry point running the asyncio event loop."""
        return asyncio.run(self.run_async())
