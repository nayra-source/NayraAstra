"""Step-by-step wizard for creating a new engagement."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nayraastra.cli.keybindings import KEY_BACK_ZERO, KEY_CANCEL
from nayraastra.cli.navigation import Navigation, Pop, Screen, Stay
from nayraastra.cli.rendering import (
    render_breadcrumb,
    render_error_panel,
    render_footer_hints,
    safe_text,
)
from nayraastra.cli.widgets.prompts import prompt_field
from nayraastra.cli.widgets.tables import render_scope_table
from nayraastra.core.domain.models import RulesOfEngagement, ScopeEntry
from nayraastra.core.domain.types import Intrusiveness, ScopeEntryKind
from nayraastra.runtime import Runtime, ValidationFailure, normalize_target

if TYPE_CHECKING:
    from rich.console import Console

    from nayraastra.cli.input import InputDriver
    from nayraastra.cli.state import SessionState


def parse_time_shortcut(raw: str, ref_time: datetime | None = None) -> datetime | None:
    """Parse ISO date strings or shortcuts like 'now', '+7d', '+24h' into timezone-aware UTC datetime."""
    text = raw.strip()
    if not text:
        return None

    now = ref_time or datetime.now(UTC)
    if text.lower() == "now":
        return now

    match = re.match(r"^\+(\d+)([dh])$", text.lower())
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit == "d":
            return now + timedelta(days=amount)
        if unit == "h":
            return now + timedelta(hours=amount)

    try:
        # Try parsing ISO formats
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError as exc:
        raise ValueError(
            f"Invalid date/time format: '{raw}'. Use ISO format (YYYY-MM-DDTHH:MM:SS) or shortcuts ('now', '+7d', '+24h')."
        ) from exc


@dataclass
class WizardData:
    """In-progress wizard configuration."""

    name: str = ""
    client: str = ""
    auth_reference: str = ""
    window_start: datetime | None = None
    window_end: datetime | None = None
    max_intrusiveness: Intrusiveness = Intrusiveness.ACTIVE_SAFE
    disruptive_enabled: bool = False
    scope_entries: list[ScopeEntry] = field(default_factory=list)


class EngagementWizardScreen(Screen):
    """Interactive wizard for defining and creating a new engagement."""

    title = "New Engagement Wizard"
    breadcrumb_title = "Create Wizard"

    def __init__(self) -> None:
        self.data = WizardData()
        self.step: int = 1
        self.notice: str | None = None

    def render(self, state: SessionState, console: Console) -> None:
        console.print(render_breadcrumb(["NAYRAASTRA", "Engagement", "New Engagement Wizard"]))

        if self.notice:
            console.print(render_error_panel(self.notice, title="Notice"))
            self.notice = None

        if self.step == 1:
            self._render_step_info(console)
        elif self.step == 2:
            self._render_scope_step(console)
        elif self.step == 3:
            self._render_review_step(console)

        console.print(render_footer_hints((("[0]", "Cancel Wizard"), ("[Ctrl+C]", "Cancel"))))

    def _render_step_info(self, console: Console) -> None:
        panel = Panel(
            Text(
                "Welcome to the Engagement Setup Wizard.\n"
                "You will configure the engagement name, client, authorization ticket, time window, "
                "intrusiveness limit, and target scope.\n\n"
                "Press Enter to proceed with each field. Enter '0' at any prompt to cancel.",
                style="white",
            ),
            title="[bold cyan]Step 1: Engagement Information[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )
        console.print(panel)

    def _render_scope_step(self, console: Console) -> None:
        console.print(render_scope_table(self.data.scope_entries))
        menu = Text()
        menu.append("\nScope Configuration Options:\n", style="bold white")
        menu.append("  1) Add target entry\n", style="bold cyan")
        menu.append("  2) Remove last target entry\n", style="bold yellow")
        menu.append("  3) Finish scope and review\n", style="bold green")
        menu.append("  0) Cancel wizard\n", style="bold red")
        console.print(menu)

    def _render_review_step(self, console: Console) -> None:
        table = Table(
            title="Review Engagement Specifications", show_header=False, box=None, padding=(0, 1)
        )
        table.add_column("Property", style="bold cyan", width=22)
        table.add_column("Value", style="white")

        table.add_row("Engagement Name:", safe_text(self.data.name))
        table.add_row("Client / Owner:", safe_text(self.data.client))
        table.add_row("Authorization Ref:", safe_text(self.data.auth_reference))
        start_s = (
            self.data.window_start.strftime("%Y-%m-%d %H:%M:%S UTC")
            if self.data.window_start
            else "Immediate"
        )
        end_s = (
            self.data.window_end.strftime("%Y-%m-%d %H:%M:%S UTC")
            if self.data.window_end
            else "Indefinite"
        )
        table.add_row("Time Window:", f"{start_s}  to  {end_s}")
        table.add_row("Max Intrusiveness:", safe_text(self.data.max_intrusiveness.value))
        table.add_row(
            "Disruptive Double Opt-In:", "ENABLED" if self.data.disruptive_enabled else "DISABLED"
        )
        table.add_row("Scope Entries:", str(len(self.data.scope_entries)))

        console.print(
            Panel(
                table,
                title="[bold green]Final Review[/bold green]",
                border_style="green",
                padding=(0, 1),
            )
        )
        console.print(render_scope_table(self.data.scope_entries))

    async def handle(
        self,
        input_str: str,
        state: SessionState,
        driver: InputDriver,
        runtime: Runtime,
    ) -> Navigation:
        ch = input_str.strip()
        if ch in (KEY_BACK_ZERO, KEY_CANCEL):
            return Pop()

        if self.step == 1:
            return await self._handle_info_step(ch, driver, runtime)
        if self.step == 2:
            return await self._handle_scope_step(ch, driver, runtime)
        if self.step == 3:
            return await self._handle_review_step(ch, driver, runtime, state)

        return Stay()

    async def _handle_info_step(self, ch: str, driver: InputDriver, runtime: Runtime) -> Navigation:
        # 1. Name
        name: str | None
        if ch and ch != "1":
            name = ch
        else:
            name = await prompt_field(driver, "Engagement Name")

        if not name or name == KEY_BACK_ZERO:
            return Pop()
        self.data.name = name

        # 2. Client
        client = await prompt_field(driver, "Client / Organization Name")
        if not client or client == KEY_BACK_ZERO:
            return Pop()
        self.data.client = client

        # 3. Auth Reference (mandatory)
        auth_ref = await prompt_field(
            driver, "Authorization Reference (Ticket/Letter ID, required)"
        )
        if not auth_ref or auth_ref == KEY_BACK_ZERO:
            return Pop()
        self.data.auth_reference = auth_ref

        # 4. Window Start
        ref_now = runtime.clock.now()
        start_val = await prompt_field(
            driver, "Window Start (ISO, 'now', '+1h', or empty for immediate)", required=False
        )
        if start_val == KEY_BACK_ZERO:
            return Pop()
        if start_val:
            try:
                self.data.window_start = parse_time_shortcut(start_val, ref_time=ref_now)
            except ValueError as exc:
                self.notice = str(exc)
                return Stay()

        # 5. Window End
        end_val = await prompt_field(
            driver, "Window End (ISO, '+7d', or empty for indefinite)", required=False
        )
        if end_val == KEY_BACK_ZERO:
            return Pop()
        if end_val:
            try:
                dt_end = parse_time_shortcut(end_val, ref_time=self.data.window_start or ref_now)
                if self.data.window_start and dt_end and dt_end <= self.data.window_start:
                    self.notice = "Window End must be strictly after Window Start."
                    return Stay()
                self.data.window_end = dt_end
            except ValueError as exc:
                self.notice = str(exc)
                return Stay()

        # 6. Max Intrusiveness
        int_choice = await prompt_field(
            driver,
            "Max Intrusiveness (1: passive, 2: active-safe, 3: active-intrusive, 4: disruptive)",
            default="2",
        )
        if int_choice == KEY_BACK_ZERO:
            return Pop()

        choice_map = {
            "1": Intrusiveness.PASSIVE,
            "2": Intrusiveness.ACTIVE_SAFE,
            "3": Intrusiveness.ACTIVE_INTRUSIVE,
            "4": Intrusiveness.DISRUPTIVE,
            "passive": Intrusiveness.PASSIVE,
            "active-safe": Intrusiveness.ACTIVE_SAFE,
            "active-intrusive": Intrusiveness.ACTIVE_INTRUSIVE,
            "disruptive": Intrusiveness.DISRUPTIVE,
        }
        choice_str = (int_choice or "2").lower()
        self.data.max_intrusiveness = choice_map.get(choice_str, Intrusiveness.ACTIVE_SAFE)

        # 7. Disruptive Opt-In confirmation if disruptive chosen
        if self.data.max_intrusiveness == Intrusiveness.DISRUPTIVE:
            # Must type exact engagement name
            confirmed = await driver.confirm_phrase(
                f"Type '{self.data.name}' to enable disruptive operations:",
                expected_phrase=self.data.name,
            )
            if not confirmed:
                self.notice = "Disruptive confirmation did not match engagement name. Reverting to active-safe."
                self.data.max_intrusiveness = Intrusiveness.ACTIVE_SAFE
                self.data.disruptive_enabled = False
            else:
                self.data.disruptive_enabled = True

        self.step = 2
        return Stay()

    async def _handle_scope_step(
        self, choice: str, driver: InputDriver, runtime: Runtime
    ) -> Navigation:
        ch = choice.strip()
        if ch in (KEY_BACK_ZERO, KEY_CANCEL):
            return Pop()

        if ch == "1":
            # Add target entry
            target_str = await prompt_field(driver, "Target (IP, CIDR, domain, e.g. 10.10.0.0/24)")
            if not target_str:
                return Stay()

            try:
                norm_target = normalize_target(target_str)
            except ValidationFailure as exc:
                self.notice = f"Invalid target: {exc}"
                return Stay()

            in_scope = await driver.confirm("Is this target IN-SCOPE?", default=True)
            note = await prompt_field(driver, "Optional note / description", required=False) or ""

            kind = ScopeEntryKind(norm_target.kind.value)
            entry = ScopeEntry(
                id=runtime.id_gen.generate(),
                engagement_id="",
                kind=kind,
                value=norm_target.raw,
                in_scope=in_scope,
                note=note,
                created_at=runtime.clock.now(),
            )
            self.data.scope_entries.append(entry)
            return Stay()

        if ch == "2":
            if self.data.scope_entries:
                self.data.scope_entries.pop()
            return Stay()

        if ch == "3":
            if not any(e.in_scope for e in self.data.scope_entries):
                self.notice = (
                    "Engagement must have at least ONE in-scope target entry before continuing."
                )
                return Stay()
            self.step = 3
            return Stay()

        return Stay()

    async def _handle_review_step(
        self, ch: str, driver: InputDriver, runtime: Runtime, state: SessionState
    ) -> Navigation:
        ch_lower = ch.strip().lower()
        if ch_lower in (KEY_BACK_ZERO, "n", "no", "q"):
            return Pop()

        if ch_lower in ("y", "yes"):
            confirmed = True
        else:
            confirmed = await driver.confirm("Confirm and create engagement?", default=True)

        if not confirmed:
            return Pop()

        roe = RulesOfEngagement(
            window_start=self.data.window_start,
            window_end=self.data.window_end,
            max_intrusiveness=self.data.max_intrusiveness,
            disruptive_enabled=self.data.disruptive_enabled,
        )

        try:
            eng = runtime.engagements.create(
                name=self.data.name,
                client=self.data.client,
                auth_reference=self.data.auth_reference,
                roe=roe,
                scope_entries=self.data.scope_entries,
            )
            session = runtime.open_engagement(eng.id)
            state.set_session(session, eng, self.data.scope_entries)
            return Pop()
        except Exception as exc:
            self.notice = f"Failed to create engagement: {exc}"
            return Stay()
