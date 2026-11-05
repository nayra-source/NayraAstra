"""Command-line interface for NAYRAASTRA (Phase 0 minimal entry point).

Commands
--------
nayraastra --version
    Print version string and exit 0.

nayraastra doctor
    Display a Rich table with environment diagnostics.

nayraastra init-db [--path PATH]
    Initialise / migrate the SQLite database.

``python -m nayraastra`` delegates here via ``__main__.py``.

Phase 2+ will replace the argparse shell with a Prompt Toolkit TUI.
See ADR-004 in docs/DECISIONS.md.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

import nayraastra
from nayraastra.core.config import load_config
from nayraastra.core.errors import ConfigError, NayraastraError
from nayraastra.core.paths import ensure_home, get_default_db_path
from nayraastra.db.connection import connect
from nayraastra.db.migrator import current_version, migrate
from nayraastra.runtime import build_runtime

console = Console()

# External tools checked by ``doctor``.
_EXTERNAL_TOOLS = ["nmap", "tshark", "bettercap", "hping3"]


# ---------------------------------------------------------------------------
# Sub-command implementations
# ---------------------------------------------------------------------------


def _cmd_doctor() -> int:
    """Run the ``doctor`` diagnostic command."""
    table = Table(title="NAYRAASTRA – System Doctor", show_header=True, header_style="bold cyan")
    table.add_column("Check", style="dim", width=30)
    table.add_column("Status")
    table.add_column("Detail")

    # Python version
    py_ver = sys.version.split()[0]
    major, minor = sys.version_info.major, sys.version_info.minor
    py_ok = major >= 3 and minor >= 11
    table.add_row(
        "Python version",
        "[green]OK[/green]" if py_ok else "[red]FAIL[/red]",
        f"{py_ver} ({'>=3.11 ✓' if py_ok else '<3.11 required'})",
    )

    # Config load
    cfg = None
    try:
        cfg = load_config()
        table.add_row("Config loaded", "[green]OK[/green]", "default.yaml + user overrides")
    except ConfigError as exc:
        table.add_row("Config loaded", "[red]FAIL[/red]", str(exc))

    # Home directory
    home = None
    try:
        home = ensure_home()
        table.add_row("Home directory", "[green]OK[/green]", str(home))
    except Exception as exc:  # noqa: BLE001
        table.add_row("Home directory", "[red]FAIL[/red]", str(exc))

    # DB init and migration
    if cfg is not None and home is not None:
        db_path = home / cfg.database.filename
        try:
            conn = connect(
                db_path, wal=cfg.database.wal, busy_timeout_ms=cfg.database.busy_timeout_ms
            )
            applied = migrate(conn)
            ver = current_version(conn)
            conn.close()
            detail = f"schema v{ver}"
            if applied:
                detail += f" (+{len(applied)} applied)"
            table.add_row("DB initialised", "[green]OK[/green]", detail)
        except NayraastraError as exc:
            table.add_row("DB initialised", "[red]FAIL[/red]", str(exc))
    else:
        table.add_row("DB initialised", "[yellow]SKIP[/yellow]", "config or home unavailable")

    # External tools
    for tool in _EXTERNAL_TOOLS:
        tool_path = shutil.which(tool)
        if tool_path:
            table.add_row(f"Tool: {tool}", "[green]FOUND[/green]", tool_path)
        else:
            table.add_row(
                f"Tool: {tool}", "[yellow]MISSING[/yellow]", "not in PATH (informational)"
            )

    # Registered Adapters
    try:
        rt = build_runtime(home=home, config=cfg)
        adapters = rt.registry.list_all()
        adp_names = ", ".join(a.name for a in adapters) if adapters else "none"
        table.add_row("Registered adapters", "[green]OK[/green]", adp_names)
        fake_status = (
            "enabled"
            if (cfg and cfg.adapters.fake_enabled) or os.environ.get("NAYRAASTRA_DEV") == "1"
            else "disabled"
        )
        table.add_row(
            "Fake adapter",
            "[green]ENABLED[/green]" if fake_status == "enabled" else "[dim]DISABLED[/dim]",
            fake_status,
        )
        rt.close()
    except Exception as exc:  # noqa: BLE001
        table.add_row("Registered adapters", "[red]FAIL[/red]", str(exc))

    console.print(table)
    return 0


def _cmd_init_db(db_path: Path) -> int:
    """Run ``init-db`` command."""
    try:
        cfg = load_config()
        conn = connect(db_path, wal=cfg.database.wal, busy_timeout_ms=cfg.database.busy_timeout_ms)
        applied = migrate(conn)
        ver = current_version(conn)
        conn.close()
    except NayraastraError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1

    if applied:
        console.print(f"[green]✓[/green] Applied {len(applied)} migration(s): {', '.join(applied)}")
    else:
        console.print("[green]✓[/green] Database already up to date.")
    console.print(f"  Schema version: {ver}")
    console.print(f"  Database: {db_path}")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate sub-command.

    Parameters
    ----------
    argv:
        Argument list (defaults to ``sys.argv[1:]``).

    Returns
    -------
    int
        Exit code (0 = success).
    """
    parser = argparse.ArgumentParser(
        prog="nayraastra",
        description="NAYRAASTRA – Pentesting Automation & Orchestration Framework",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"NAYRAASTRA {nayraastra.__version__}",
    )

    sub = parser.add_subparsers(dest="command")

    # doctor
    sub.add_parser("doctor", help="Print a system diagnostic table.")

    # init-db
    init_db_parser = sub.add_parser("init-db", help="Initialise / migrate the database.")
    init_db_parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Path to the SQLite database file (default: $NAYRAASTRA_HOME/nayraastra.db).",
    )

    args = parser.parse_args(argv)

    if args.command == "doctor":
        return _cmd_doctor()

    if args.command == "init-db":
        db_path = args.path if args.path is not None else get_default_db_path()
        return _cmd_init_db(db_path)

    # No sub-command – show help.
    parser.print_help()
    return 0
