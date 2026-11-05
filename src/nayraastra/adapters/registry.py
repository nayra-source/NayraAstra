"""Central catalog and discovery registry for tool adapters."""

from __future__ import annotations

from typing import Any

from nayraastra.adapters.base import ToolAdapter
from nayraastra.core.domain.types import Capability
from nayraastra.core.errors import ValidationFailure


class AdapterRegistry:
    """Registry maintaining active tool adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, ToolAdapter] = {}

    def register(self, adapter: ToolAdapter) -> None:
        """Register an adapter. Rejects duplicate names."""
        name = adapter.name
        if name in self._adapters:
            raise ValidationFailure(
                f"Adapter with name {name!r} is already registered.",
                details={"adapter_name": name},
            )
        self._adapters[name] = adapter

    def get(self, name: str) -> ToolAdapter | None:
        """Retrieve an adapter by its registered name."""
        return self._adapters.get(name)

    def list_all(self) -> list[ToolAdapter]:
        """Return all registered adapters."""
        return list(self._adapters.values())

    def for_capability(self, capability: Capability) -> list[ToolAdapter]:
        """Find adapters offering the requested capability.

        Installed adapters are prioritized first.
        """
        matching: list[ToolAdapter] = []
        for adapter in self._adapters.values():
            if capability in adapter.capabilities:
                matching.append(adapter)

        # Sort: installed=True first, then alphabetically by name
        def _sort_key(adp: ToolAdapter) -> tuple[int, str]:
            try:
                status = adp.check_installed()
                is_inst = 0 if status.installed else 1
            except Exception:
                is_inst = 1
            return (is_inst, adp.name)

        return sorted(matching, key=_sort_key)

    def describe(self) -> list[dict[str, Any]]:
        """Return structured summary for all adapters."""
        res: list[dict[str, Any]] = []
        for adp in self._adapters.values():
            try:
                status = adp.check_installed()
            except Exception as exc:
                status_dict = {"installed": False, "error": str(exc)}
            else:
                status_dict = status.model_dump()

            res.append(
                {
                    "name": adp.name,
                    "capabilities": [c.value for c in adp.capabilities],
                    "intrusiveness": adp.intrusiveness.value,
                    "status": status_dict,
                }
            )
        return res
