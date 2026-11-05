"""Safe subprocess execution runner with environment scrubbing and process group isolation."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from nayraastra.core.errors import ValidationFailure

_DEFAULT_ENV_ALLOWLIST = frozenset(
    {"PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT", "VIRTUAL_ENV"}
)


class ProcessResult(BaseModel, frozen=True, extra="forbid"):
    """Result of external command execution."""

    exit_code: int
    stdout: bytes
    stderr: bytes
    duration_seconds: float
    timed_out: bool = False
    cancelled: bool = False


class ProcessRunner:
    """Safely executes processes using argument lists only (shell=False)."""

    async def run(
        self,
        argv: list[str],
        *,
        timeout: float = 300.0,
        max_output_bytes: int = 10 * 1024 * 1024,
        env_allowlist: set[str] | frozenset[str] | None = None,
        cwd: Path | None = None,
        on_line: Callable[[str], None] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> ProcessResult:
        """Run an external command safely without a shell."""
        if not argv:
            raise ValidationFailure("Argument list cannot be empty.")

        # Resolve binary path
        cmd_path = argv[0]
        resolved_bin = shutil.which(cmd_path)
        if not resolved_bin:
            raise ValidationFailure(
                f"Binary {cmd_path!r} not found in PATH or not executable.",
                details={"cmd": cmd_path},
            )

        # Ensure argv[0] is absolute path
        clean_argv = [os.path.abspath(resolved_bin)] + list(argv[1:])

        # Scrub environment: only retain allowlisted variables
        allowed_keys = env_allowlist or _DEFAULT_ENV_ALLOWLIST
        scrubbed_env = {k: v for k, v in os.environ.items() if k in allowed_keys}

        start_time = time.monotonic()
        timed_out = False
        cancelled = False

        # Launch process in a new process group for clean group termination
        proc = await asyncio.create_subprocess_exec(
            *clean_argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
            env=scrubbed_env,
            start_new_session=True,
        )

        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        total_stdout = 0
        total_stderr = 0

        async def _read_stream(
            stream: asyncio.StreamReader,
            chunks: list[bytes],
            is_stdout: bool,
        ) -> None:
            nonlocal total_stdout, total_stderr
            while not stream.at_eof():
                line_bytes = await stream.readline()
                if not line_bytes:
                    break

                if is_stdout:
                    if total_stdout < max_output_bytes:
                        chunks.append(line_bytes[: max_output_bytes - total_stdout])
                        total_stdout += len(line_bytes)
                    if on_line:
                        with contextlib.suppress(Exception):
                            line_str = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
                            on_line(line_str)
                elif total_stderr < max_output_bytes:
                    chunks.append(line_bytes[: max_output_bytes - total_stderr])
                    total_stderr += len(line_bytes)

        async def _kill_process_group() -> None:
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
                await asyncio.sleep(0.3)
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()

        read_tasks = [
            asyncio.create_task(_read_stream(proc.stdout, stdout_chunks, True))
            if proc.stdout
            else asyncio.sleep(0),
            asyncio.create_task(_read_stream(proc.stderr, stderr_chunks, False))
            if proc.stderr
            else asyncio.sleep(0),
        ]

        watch_tasks: list[asyncio.Task[Any]] = []
        cancel_task: asyncio.Task[bool] | None = None
        if cancel_event is not None:
            cancel_task = asyncio.create_task(cancel_event.wait())
            watch_tasks.append(cancel_task)

        try:
            wait_proc = asyncio.create_task(proc.wait())
            watch_tasks.append(wait_proc)
            done, _ = await asyncio.wait(
                watch_tasks,
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if (
                cancel_task is not None
                and cancel_task in done
                and cancel_event
                and cancel_event.is_set()
            ):
                cancelled = True
                await _kill_process_group()
                await proc.wait()
            elif wait_proc not in done:
                timed_out = True
                await _kill_process_group()
                await proc.wait()
        except TimeoutError:
            timed_out = True
            await _kill_process_group()
            await proc.wait()
        finally:
            if cancel_task is not None:
                cancel_task.cancel()
            await asyncio.gather(*read_tasks, return_exceptions=True)

        duration = time.monotonic() - start_time
        exit_code = proc.returncode if proc.returncode is not None else -1

        return ProcessResult(
            exit_code=exit_code,
            stdout=b"".join(stdout_chunks),
            stderr=b"".join(stderr_chunks),
            duration_seconds=duration,
            timed_out=timed_out,
            cancelled=cancelled,
        )
