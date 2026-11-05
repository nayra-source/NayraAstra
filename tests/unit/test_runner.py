"""Unit tests for ProcessRunner."""

from __future__ import annotations

import asyncio
import sys

import pytest

from nayraastra.core.errors import ValidationFailure
from nayraastra.core.execution.runner import ProcessRunner


@pytest.mark.unit
class TestProcessRunner:
    @pytest.fixture()
    def runner(self) -> ProcessRunner:
        return ProcessRunner()

    def test_successful_run(self, runner: ProcessRunner) -> None:
        async def _test() -> None:
            cmd = [sys.executable, "-c", "print('hello from runner')"]
            res = await runner.run(cmd)
            assert res.exit_code == 0
            assert b"hello from runner" in res.stdout
            assert not res.timed_out
            assert not res.cancelled

        asyncio.run(_test())

    def test_no_shell_metacharacter_safety(self, runner: ProcessRunner) -> None:
        async def _test() -> None:
            # Metacharacters in arguments must be treated as literal strings, not executed!
            cmd = [
                sys.executable,
                "-c",
                "import sys; print(sys.argv[1])",
                "hello; rm -rf /; echo $HOME | cat",
            ]
            res = await runner.run(cmd)
            assert res.exit_code == 0
            assert b"hello; rm -rf /; echo $HOME | cat" in res.stdout

        asyncio.run(_test())

    def test_env_scrubbing(self, runner: ProcessRunner, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _test() -> None:
            monkeypatch.setenv("SECRET_LEAK_TEST", "SUPER_SECRET_VALUE")
            cmd = [
                sys.executable,
                "-c",
                "import os; print('SECRET=' + os.environ.get('SECRET_LEAK_TEST', 'NONE'))",
            ]
            res = await runner.run(cmd)
            assert res.exit_code == 0
            assert b"SECRET=NONE" in res.stdout

        asyncio.run(_test())

    def test_output_capping(self, runner: ProcessRunner) -> None:
        async def _test() -> None:
            cmd = [sys.executable, "-c", "print('A' * 1000)"]
            res = await runner.run(cmd, max_output_bytes=50)
            assert res.exit_code == 0
            assert len(res.stdout) == 50

        asyncio.run(_test())

    def test_timeout_kills_process(self, runner: ProcessRunner) -> None:
        async def _test() -> None:
            cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
            res = await runner.run(cmd, timeout=0.1)
            assert res.timed_out
            assert res.exit_code != 0

        asyncio.run(_test())

    def test_cancellation(self, runner: ProcessRunner) -> None:
        async def _test() -> None:
            cancel_event = asyncio.Event()

            async def _trigger_cancel() -> None:
                await asyncio.sleep(0.05)
                cancel_event.set()

            asyncio.create_task(_trigger_cancel())
            cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
            res = await runner.run(cmd, cancel_event=cancel_event, timeout=5.0)
            assert res.cancelled

        asyncio.run(_test())

    def test_rejects_empty_argv(self, runner: ProcessRunner) -> None:
        async def _test() -> None:
            with pytest.raises(ValidationFailure):
                await runner.run([])

        asyncio.run(_test())

    def test_rejects_nonexistent_binary(self, runner: ProcessRunner) -> None:
        async def _test() -> None:
            with pytest.raises(ValidationFailure):
                await runner.run(["non_existent_binary_123456789"])

        asyncio.run(_test())
