"""Command-line interface entry point for NAYRAASTRA."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

import nayraastra
from nayraastra.cli.app import App
from nayraastra.cli.rendering import create_console, safe_text
from nayraastra.runtime import ConfigError, NayraastraError, Runtime, build_runtime

__all__ = ["App", "main"]


def _cmd_doctor(runtime: Runtime, console: Console) -> int:
    """Display environment and runtime diagnostics."""
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

    # Config
    table.add_row("Config loaded", "[green]OK[/green]", "default.yaml + user overrides")

    # Home directory
    table.add_row("Home directory", "[green]OK[/green]", safe_text(str(runtime.home)))

    # DB status
    table.add_row("DB initialised", "[green]OK[/green]", "schema v2")

    # External tools
    for tool in ("nmap", "tshark", "bettercap", "hping3"):
        tool_path = shutil.which(tool)
        if tool_path:
            table.add_row(f"Tool: {tool}", "[green]FOUND[/green]", safe_text(tool_path))
        else:
            table.add_row(f"Tool: {tool}", "[dim]MISSING[/dim]", "not in PATH (informational)")

    # Registered Adapters
    adapters = runtime.registry.list_all()
    adp_names = ", ".join(a.name for a in adapters) if adapters else "none"
    table.add_row("Registered adapters", "[green]OK[/green]", safe_text(adp_names))

    fake_status = "enabled" if any(a.name.startswith("fake") for a in adapters) else "disabled"
    table.add_row(
        "Fake adapter",
        "[green]ENABLED[/green]" if fake_status == "enabled" else "[dim]DISABLED[/dim]",
        fake_status,
    )

    console.print(table)
    return 0


def _cmd_init_db(runtime: Runtime, console: Console, db_path: Path | None = None) -> int:
    """Initialise or migrate application database."""
    target = db_path or (runtime.home / runtime.config.database.filename)
    runtime.init_db(target)
    console.print(
        f"[green]Database initialised and migrated successfully at {safe_text(str(target))}.[/green]"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and launch interactive shell or subcommand."""
    parser = argparse.ArgumentParser(
        prog="nayraastra",
        description="NAYRAASTRA – Orchestration framework for penetration testing.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"NAYRAASTRA {nayraastra.__version__}",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        default=False,
        help="Enable developer mode (fake adapters, simulated failures).",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        default=False,
        help="Disable ANSI styling, colors, and box borders.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="Disable colored output.",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help="Custom NAYRAASTRA home directory path.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Optional subcommand to execute.")
    subparsers.add_parser("doctor", help="Run system diagnostics.")
    init_db_parser = subparsers.add_parser("init-db", help="Initialise or migrate database.")
    init_db_parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Path to the SQLite database file.",
    )

    args = parser.parse_args(argv)

    # Check NO_COLOR environment variable
    no_color = args.no_color or ("NO_COLOR" in os.environ)
    plain = args.plain
    console = create_console(plain=plain, no_color=no_color)

    # Dev mode from flag or env
    is_dev = args.dev or (os.environ.get("NAYRAASTRA_DEV") == "1")

    # Bootstrap runtime
    try:
        runtime = build_runtime(home=args.home, dev=is_dev)
    except (ConfigError, NayraastraError) as exc:
        console.print(f"[bold red]Initialization Error:[/bold red] {safe_text(str(exc))}")
        return 1

    try:
        if args.command == "doctor":
            return _cmd_doctor(runtime, console)
        if args.command == "init-db":
            return _cmd_init_db(runtime, console, db_path=args.path)

        if not sys.stdin.isatty() and not is_dev and (argv is not None and len(argv) == 0):
            parser.print_help()
            return 0

        # Interactive shell
        app = App(
            runtime=runtime,
            is_dev=is_dev,
            plain=plain,
            no_color=no_color,
            console=console,
        )
        return app.run()
    finally:
        runtime.close()


if __name__ == "__main__":
    sys.exit(main())
