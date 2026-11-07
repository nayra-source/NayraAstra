"""Module capability screens (Recon, Enumeration, Analysis) with locked indicators."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nayraastra.cli.keybindings import GLOBAL_KEY_HINTS, KEY_BACK_ESC, KEY_BACK_ZERO
from nayraastra.cli.navigation import Navigation, Pop, Push, Screen, Stay
from nayraastra.cli.rendering import (
    render_breadcrumb,
    render_error_panel,
    render_footer_hints,
)
from nayraastra.cli.screens.run_flow import RunFlowScreen
from nayraastra.cli.widgets.menu import MenuItem, render_menu
from nayraastra.core.domain.types import Capability, Intrusiveness

if TYPE_CHECKING:
    from rich.console import Console

    from nayraastra.cli.input import InputDriver
    from nayraastra.cli.state import SessionState
    from nayraastra.runtime import Runtime

_CATEGORY_CAPABILITIES: dict[str, list[tuple[Capability, str]]] = {
    "recon": [
        (Capability.HOST_DISCOVERY, "Host Discovery (Ping Sweep / ARP)"),
        (Capability.DNS_LOOKUP, "DNS Lookup & Resolution"),
        (Capability.HTTP_PROBE, "HTTP / Web Service Probe"),
    ],
    "enumeration": [
        (Capability.PORT_SCAN, "TCP / UDP Port Scan"),
        (Capability.SERVICE_DETECT, "Service Version Detection"),
    ],
    "analysis": [
        (Capability.PCAP_ANALYSIS, "Packet Capture / Traffic Analysis"),
    ],
}


class ModuleMenuScreen(Screen):
    """Lists security actions for a category, highlighting available and locked capabilities."""

    def __init__(self, module_name: str, category: str) -> None:
        self.module_name = module_name
        self.category = category
        self.title = module_name
        self.breadcrumb_title = module_name
        self.notice: str | None = None

    def render(self, state: SessionState, console: Console) -> None:
        console.print(render_breadcrumb(["NAYRAASTRA", self.module_name]))

        if self.notice:
            console.print(render_error_panel(self.notice, title="Notice"))
            self.notice = None

        items: list[MenuItem] = []
        caps = _CATEGORY_CAPABILITIES.get(self.category, [])

        max_ceiling = (
            state.engagement.roe.max_intrusiveness
            if (state.engagement and state.engagement.roe)
            else Intrusiveness.ACTIVE_SAFE
        )
        is_closed = state.engagement.status != "active" if state.engagement else False

        for idx, (cap, label) in enumerate(caps, 1):
            locked = False
            lock_reason = None

            if is_closed:
                locked = True
                lock_reason = "engagement is not active"
            elif not state.engagement:
                locked = True
                lock_reason = "no engagement open"
            else:
                # Check if an adapter exists supporting this capability
                # We will check if any adapter is registered in the session registry
                adapters = state.session.registry.for_capability(cap) if state.session else []
                if not adapters:
                    locked = True
                    lock_reason = "missing adapter"
                else:
                    # Check if adapter intrusiveness exceeds ceiling
                    min_int = min(a.intrusiveness for a in adapters)
                    if min_int > max_ceiling:
                        locked = True
                        lock_reason = f"exceeds ROE limit ({min_int.value} > {max_ceiling.value})"

            items.append(
                MenuItem(
                    key=str(idx),
                    label=label,
                    locked=locked,
                    lock_reason=lock_reason,
                )
            )

        items.append(MenuItem(key="0", label="Back"))
        console.print(render_menu(items))
        console.print()
        console.print(render_footer_hints(GLOBAL_KEY_HINTS))

    async def handle(
        self,
        input_str: str,
        state: SessionState,
        driver: InputDriver,
        runtime: Runtime,
    ) -> Navigation:
        ch = input_str.strip().lower()

        if ch in (KEY_BACK_ZERO, KEY_BACK_ESC):
            return Pop()

        caps = _CATEGORY_CAPABILITIES.get(self.category, [])
        if ch.isdigit():
            idx = int(ch) - 1
            if 0 <= idx < len(caps):
                selected_cap, cap_label = caps[idx]

                if not state.session or not state.engagement:
                    self.notice = "Open an engagement before running tasks."
                    return Stay()

                adapters = state.session.registry.for_capability(selected_cap)
                if not adapters:
                    self.notice = f"No adapter registered for capability '{selected_cap.value}'."
                    return Stay()

                # Pick adapter
                adapter = adapters[0]
                max_ceiling = state.engagement.roe.max_intrusiveness
                if adapter.intrusiveness > max_ceiling:
                    self.notice = f"Action locked: requires ROE ceiling {adapter.intrusiveness.value} (currently {max_ceiling.value})."
                    return Stay()

                return Push(
                    RunFlowScreen(
                        module_name=self.module_name,
                        capability=selected_cap,
                        capability_label=cap_label,
                        adapter=adapter,
                    )
                )

        return Stay()
