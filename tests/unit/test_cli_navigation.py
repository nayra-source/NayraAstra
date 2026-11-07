"""Unit tests for screen navigation, stack push/pop, breadcrumbs, and back handling."""

from __future__ import annotations

import asyncio

import pytest
from rich.console import Console

from nayraastra.cli.input import InputDriver, ScriptedInputDriver
from nayraastra.cli.keybindings import KEY_BACK_ESC, KEY_BACK_ZERO
from nayraastra.cli.navigation import Exit, Navigation, Navigator, Pop, Screen, Stay
from nayraastra.cli.screens.help import HelpScreen
from nayraastra.cli.screens.main_menu import MainMenuScreen
from nayraastra.cli.screens.placeholder import PlaceholderScreen
from nayraastra.cli.state import SessionState
from nayraastra.runtime import Runtime


class DummyScreen(Screen):
    def __init__(self, name: str) -> None:
        self.title = name
        self.breadcrumb_title = name

    def render(self, state: SessionState, console: Console) -> None:
        pass

    async def handle(
        self,
        input_str: str,
        state: SessionState,
        driver: InputDriver,
        runtime: Runtime,
    ) -> Navigation:
        if input_str in (KEY_BACK_ZERO, KEY_BACK_ESC):
            return Pop()
        return Stay()


@pytest.mark.unit
class TestNavigator:
    def test_initial_navigator_state(self) -> None:
        root = DummyScreen("Root")
        nav = Navigator(root)

        assert nav.current is root
        assert nav.depth == 1
        assert nav.is_root is True
        assert nav.breadcrumbs() == ["Root"]

    def test_push_and_breadcrumbs(self) -> None:
        root = DummyScreen("Root")
        nav = Navigator(root)

        sub1 = DummyScreen("Sub1")
        nav.push(sub1)
        assert nav.depth == 2
        assert nav.is_root is False
        assert nav.current is sub1
        assert nav.breadcrumbs() == ["Root", "Sub1"]

        sub2 = DummyScreen("Sub2")
        nav.push(sub2)
        assert nav.depth == 3
        assert nav.breadcrumbs() == ["Root", "Sub1", "Sub2"]

    def test_pop_stack(self) -> None:
        root = DummyScreen("Root")
        sub1 = DummyScreen("Sub1")
        nav = Navigator(root)
        nav.push(sub1)

        popped = nav.pop()
        assert popped is sub1
        assert nav.depth == 1
        assert nav.is_root is True
        assert nav.current is root

        # Popping at root does not remove root
        assert nav.pop() is None
        assert nav.depth == 1

    def test_replace_screen(self) -> None:
        root = DummyScreen("Root")
        nav = Navigator(root)

        sub1 = DummyScreen("Sub1")
        nav.push(sub1)

        rep = DummyScreen("Replaced")
        nav.replace(rep)
        assert nav.depth == 2
        assert nav.current is rep
        assert nav.breadcrumbs() == ["Root", "Replaced"]


@pytest.mark.unit
class TestScreenBackTraversal:
    @pytest.mark.parametrize("key", [KEY_BACK_ZERO, KEY_BACK_ESC])
    def test_placeholder_screen_back(self, key: str) -> None:
        async def _test() -> None:
            screen = PlaceholderScreen("Workflows", "Phase 5", "Description")
            state = SessionState()
            driver = ScriptedInputDriver([key])
            res = await screen.handle(key, state, driver, None)  # type: ignore[arg-type]
            assert isinstance(res, Pop)

        asyncio.run(_test())

    @pytest.mark.parametrize("key", [KEY_BACK_ZERO, KEY_BACK_ESC])
    def test_help_screen_back(self, key: str) -> None:
        async def _test() -> None:
            screen = HelpScreen()
            state = SessionState()
            driver = ScriptedInputDriver([key])
            res = await screen.handle(key, state, driver, None)  # type: ignore[arg-type]
            assert isinstance(res, Pop)

        asyncio.run(_test())

    def test_main_menu_exit_confirmed(self) -> None:
        async def _test() -> None:
            screen = MainMenuScreen()
            state = SessionState()
            driver = ScriptedInputDriver(["y"])
            res = await screen.handle(KEY_BACK_ZERO, state, driver, None)  # type: ignore[arg-type]
            assert isinstance(res, Exit)

        asyncio.run(_test())

    def test_main_menu_exit_aborted(self) -> None:
        async def _test() -> None:
            screen = MainMenuScreen()
            state = SessionState()
            driver = ScriptedInputDriver(["n"])
            res = await screen.handle(KEY_BACK_ZERO, state, driver, None)  # type: ignore[arg-type]
            assert isinstance(res, Stay)

        asyncio.run(_test())
