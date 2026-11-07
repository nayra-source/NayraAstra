"""Screen stack navigation, breadcrumbs, and lifecycle management."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

    from nayraastra.cli.input import InputDriver
    from nayraastra.cli.state import SessionState
    from nayraastra.runtime import Runtime


# ---------------------------------------------------------------------------
# Navigation Actions
# ---------------------------------------------------------------------------


class Navigation:
    """Base class for all screen navigation transitions."""


@dataclass(frozen=True)
class Push(Navigation):
    """Push a new screen onto the stack."""

    screen: Screen


@dataclass(frozen=True)
class Pop(Navigation):
    """Pop the current screen off the stack, returning to the previous screen."""


@dataclass(frozen=True)
class Replace(Navigation):
    """Replace the current screen with a new screen (same stack depth)."""

    screen: Screen


@dataclass(frozen=True)
class Stay(Navigation):
    """Remain on the current screen (e.g. after invalid input or a re-render)."""


@dataclass(frozen=True)
class Exit(Navigation):
    """Exit the application."""


# ---------------------------------------------------------------------------
# Screen Abstract Base Class
# ---------------------------------------------------------------------------


class Screen(ABC):
    """Base interface for all CLI interactive screens."""

    title: str = "NAYRAASTRA"
    breadcrumb_title: str | None = None

    def get_breadcrumb_title(self) -> str:
        """Return the label used in the breadcrumb path."""
        return self.breadcrumb_title or self.title

    @abstractmethod
    def render(self, state: SessionState, console: Console) -> None:
        """Render the screen contents to the Rich console."""
        ...

    @abstractmethod
    async def handle(
        self,
        input_str: str,
        state: SessionState,
        driver: InputDriver,
        runtime: Runtime,
    ) -> Navigation:
        """Handle a user input or selection and return a Navigation transition."""
        ...


# ---------------------------------------------------------------------------
# Navigator
# ---------------------------------------------------------------------------


class Navigator:
    """Manages the LIFO screen navigation stack and breadcrumb hierarchy."""

    def __init__(self, root_screen: Screen) -> None:
        self._stack: list[Screen] = [root_screen]

    @property
    def current(self) -> Screen:
        """Return the active top screen on the stack."""
        return self._stack[-1]

    @property
    def depth(self) -> int:
        """Return the current navigation depth."""
        return len(self._stack)

    @property
    def is_root(self) -> bool:
        """Return True if currently at the root screen."""
        return len(self._stack) <= 1

    def push(self, screen: Screen) -> None:
        """Push a new screen onto the stack."""
        self._stack.append(screen)

    def pop(self) -> Screen | None:
        """Pop the current screen off the stack if not at root."""
        if len(self._stack) > 1:
            return self._stack.pop()
        return None

    def replace(self, screen: Screen) -> None:
        """Replace the top screen."""
        if self._stack:
            self._stack[-1] = screen
        else:
            self._stack.append(screen)

    def breadcrumbs(self) -> list[str]:
        """Return the sequence of breadcrumb labels from root to current screen."""
        return [s.get_breadcrumb_title() for s in self._stack]
