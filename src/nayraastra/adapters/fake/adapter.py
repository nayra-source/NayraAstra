"""Synthetic deterministic fake adapters for testing and development."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import ClassVar

from nayraastra.adapters.base import (
    Estimate,
    RawResult,
    RunContext,
    ToolAdapter,
    ToolStatus,
)
from nayraastra.core.domain.models import ArtifactRecord, Observation, Task
from nayraastra.core.domain.types import Capability, Intrusiveness


class FakeAdapter(ToolAdapter):
    """Deterministic synthetic adapter executing no external binaries or network calls."""

    name: ClassVar[str] = "fake"
    capabilities: ClassVar[frozenset[Capability]] = frozenset(
        {Capability.HOST_DISCOVERY, Capability.PORT_SCAN, Capability.SERVICE_DETECT}
    )
    intrusiveness: ClassVar[Intrusiveness] = Intrusiveness.PASSIVE

    def __init__(self, force_missing: bool = False) -> None:
        self.force_missing = force_missing

    def check_installed(self) -> ToolStatus:
        if self.force_missing:
            return ToolStatus(
                installed=False,
                error="Fake binary missing (force_missing enabled)",
            )
        return ToolStatus(
            installed=True,
            path="/bin/fake-tool",
            version="1.0.0-synthetic",
        )

    def build_command(self, task: Task) -> list[str]:
        target_val = task.target.normalized
        return ["fake-tool", "--target", target_val, "--cap", task.capability.value]

    async def run(self, task: Task, ctx: RunContext) -> RawResult:
        # Check task-level behavior switches
        params = task.args

        if params.get("missing"):
            return RawResult(
                exit_code=127,
                stderr=b"fake-tool: command not found",
                duration_seconds=0.01,
            )

        if params.get("hang"):
            # Sleep indefinitely or until cancelled
            if ctx.cancel_event:
                await ctx.cancel_event.wait()
            else:
                await asyncio.sleep(3600)
            return RawResult(exit_code=-1, timed_out=True)

        delay = float(params.get("delay", 0.01))
        if delay > 0:
            await asyncio.sleep(delay)

        if params.get("fail"):
            ctx.emit_output("[fake] execution simulated failure")
            return RawResult(
                exit_code=1,
                stderr=b"Simulated task failure triggered by task parameter fail=True",
                duration_seconds=delay,
            )

        # Generate deterministic synthetic output based on target
        target_str = task.target.normalized
        target_hash = hashlib.sha256(target_str.encode("utf-8")).hexdigest()
        open_port = 80 if int(target_hash[:2], 16) % 2 == 0 else 443
        service_name = "http" if open_port == 80 else "https"

        lines = [
            f"[fake] scanning target {target_str}...",
            f"[fake] host {target_str} is UP",
            f"[fake] discovered port {open_port}/tcp open ({service_name})",
            "[fake] scan complete.",
        ]

        for line in lines:
            ctx.emit_output(line)
            if delay > 0:
                await asyncio.sleep(delay / 2)

        raw_output_text = "\n".join(lines) + "\n"
        raw_output_bytes = raw_output_text.encode("utf-8")

        # Create raw output artifact in workspace
        artifact_filename = f"task_{task.id}_output.txt"
        artifact_path = ctx.artifacts_dir / artifact_filename
        artifact_path.write_bytes(raw_output_bytes)

        sha256_hash = hashlib.sha256(raw_output_bytes).hexdigest()
        artifact_rel_path = f"artifacts/{artifact_filename}"

        artifact = ArtifactRecord(
            task_id=task.id,
            engagement_id=task.engagement_id,
            artifact_type="raw_output",
            mime_type="text/plain",
            path=artifact_rel_path,
            size_bytes=len(raw_output_bytes),
            sha256=sha256_hash,
            tool="fake",
            tool_version="1.0.0-synthetic",
            command_line=self.build_command(task),
            created_at=ctx.clock.now(),
        )

        return RawResult(
            exit_code=0,
            stdout=raw_output_bytes,
            duration_seconds=delay,
            artifacts=[artifact],
        )

    def parse(self, raw: RawResult) -> list[Observation]:
        observations: list[Observation] = []
        if raw.exit_code != 0:
            return observations

        text = raw.stdout.decode("utf-8", errors="replace")
        now_time = None

        # Find artifact for task and engagement info
        task_id = "unknown"
        engagement_id = "unknown"
        if raw.artifacts:
            task_id = raw.artifacts[0].task_id
            engagement_id = raw.artifacts[0].engagement_id
            now_time = raw.artifacts[0].created_at

        if not now_time:
            now_time = datetime.now(UTC)

        for line in text.splitlines():
            if "is UP" in line:
                observations.append(
                    Observation(
                        task_id=task_id,
                        engagement_id=engagement_id,
                        observation_key="host_up",
                        value={"status": "up", "detail": line},
                        confidence="confirmed",
                        observed_at=now_time,
                    )
                )
            elif "discovered port" in line:
                observations.append(
                    Observation(
                        task_id=task_id,
                        engagement_id=engagement_id,
                        observation_key="open_port",
                        value={"detail": line},
                        confidence="confirmed",
                        observed_at=now_time,
                    )
                )

        return observations

    def estimate(self, task: Task) -> Estimate:
        return Estimate(estimated_seconds=0.05, bandwidth_bytes=100)


class FakeDisruptiveAdapter(ToolAdapter):
    """Synthetic adapter with DISRUPTIVE intrusiveness for testing safety gates."""

    name: ClassVar[str] = "fake_disruptive"
    capabilities: ClassVar[frozenset[Capability]] = frozenset({Capability.HOST_DISCOVERY})
    intrusiveness: ClassVar[Intrusiveness] = Intrusiveness.DISRUPTIVE

    def check_installed(self) -> ToolStatus:
        return ToolStatus(installed=True, path="/bin/fake-disruptive", version="1.0.0")

    def build_command(self, task: Task) -> list[str]:
        return ["fake-disruptive", "--target", task.target.normalized]

    async def run(self, task: Task, ctx: RunContext) -> RawResult:
        ctx.emit_output("[fake_disruptive] running disruptive payload test...")
        return RawResult(exit_code=0, stdout=b"disruptive test payload sent")

    def parse(self, raw: RawResult) -> list[Observation]:
        return []
