"""Adapters package for security tool wrappers."""

from __future__ import annotations

from nayraastra.adapters.base import (
    Estimate,
    RawResult,
    RunContext,
    ToolAdapter,
    ToolStatus,
)
from nayraastra.adapters.nmap import NmapAdapter, parse_nmap_xml
from nayraastra.adapters.registry import AdapterRegistry

__all__ = [
    "AdapterRegistry",
    "Estimate",
    "NmapAdapter",
    "RawResult",
    "RunContext",
    "ToolAdapter",
    "ToolStatus",
    "parse_nmap_xml",
]
