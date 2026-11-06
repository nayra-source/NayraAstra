"""Nmap tool adapter implementing execution, command building, and output parsing."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

from nayraastra.adapters.base import (
    Estimate,
    RawResult,
    RunContext,
    ToolAdapter,
    ToolStatus,
)
from nayraastra.adapters.nmap.parser import parse_nmap_xml
from nayraastra.core.domain.models import ArtifactRecord, Observation, Task
from nayraastra.core.domain.types import Capability, Intrusiveness
from nayraastra.core.execution.runner import ProcessRunner

_VERSION_REGEX = re.compile(r"Nmap version\s+([^\s()]+)")


class NmapAdapter(ToolAdapter):
    """Orchestration adapter for the Nmap network scanner."""

    name: ClassVar[str] = "nmap"
    capabilities: ClassVar[frozenset[Capability]] = frozenset(
        {Capability.HOST_DISCOVERY, Capability.PORT_SCAN, Capability.SERVICE_DETECT}
    )
    intrusiveness: ClassVar[Intrusiveness] = Intrusiveness.ACTIVE_SAFE

    def __init__(self, binary_path: str | None = None) -> None:
        self.binary_path = binary_path

    def _get_binary(self) -> str | None:
        if self.binary_path:
            return self.binary_path
        return shutil.which("nmap")

    def check_installed(self) -> ToolStatus:
        """Inspect system PATH for nmap and parse nmap --version."""
        binary = self._get_binary()
        if not binary:
            return ToolStatus(
                installed=False,
                error="nmap binary not found in PATH",
            )

        try:
            res = subprocess.run(  # noqa: S603
                [binary, "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if res.returncode != 0:
                return ToolStatus(
                    installed=False,
                    path=binary,
                    error=f"nmap --version returned non-zero exit code {res.returncode}",
                )

            version = "unknown"
            match = _VERSION_REGEX.search(res.stdout)
            if match:
                version = match.group(1)

            return ToolStatus(
                installed=True,
                path=binary,
                version=version,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolStatus(
                installed=False,
                path=binary,
                error=f"Failed to execute nmap --version: {exc}",
            )

    def estimate(self, task: Task) -> Estimate:
        """Estimate execution resource requirements."""
        if task.capability == Capability.HOST_DISCOVERY:
            return Estimate(estimated_seconds=5.0, bandwidth_bytes=50_000)
        if task.capability == Capability.SERVICE_DETECT:
            return Estimate(estimated_seconds=45.0, bandwidth_bytes=2_000_000)
        return Estimate(estimated_seconds=20.0, bandwidth_bytes=500_000)

    def build_command(self, task: Task) -> list[str]:
        """Construct the argument list to execute. Never return a shell string.

        Parameters
        ----------
        task
            The task specifying target, capability, and execution args.

        Returns
        -------
        list[str]
            Safe argument vector ending with `-- <target>`.
        """
        binary = self.binary_path or "nmap"
        args: list[str] = [binary]

        task_args = task.args
        cap = task.capability

        # Capability-driven scanning mode
        if cap == Capability.HOST_DISCOVERY:
            args.append("-sn")
        elif cap == Capability.SERVICE_DETECT:
            scan_type = str(task_args.get("scan_type", "-sS"))
            args.extend([scan_type, "-sV"])
            self._apply_port_selection(args, task_args)
        else:  # Capability.PORT_SCAN
            scan_type = str(task_args.get("scan_type", "-sS"))
            args.append(scan_type)
            if task_args.get("service_detect"):
                args.append("-sV")
            self._apply_port_selection(args, task_args)

        # Timing template
        timing = task_args.get("timing")
        if timing and re.fullmatch(r"-T[0-5]", str(timing)):
            args.append(str(timing))

        # Explicit XML output path
        xml_path = str(task_args.get("xml_path", f"artifacts/nmap_{task.id}.xml"))
        args.extend(["-oX", xml_path])

        # Extra safe flags if provided
        extra = task_args.get("extra_args")
        if isinstance(extra, list):
            forbidden = set("&;|$\\><`!*?[](){}\"' ")
            for item in extra:
                item_str = str(item)
                if not any(c in forbidden for c in item_str):
                    args.append(item_str)

        # Argument injection barrier: target is strictly preceded by '--'
        target_val = task.target.normalized
        args.extend(["--", target_val])

        return args

    def _apply_port_selection(self, args: list[str], task_args: dict[str, object]) -> None:
        """Apply either explicit port range or top-ports ceiling."""
        if "ports" in task_args:
            args.extend(["-p", str(task_args["ports"])])
        else:
            top_ports = task_args.get("top_ports", 100)
            args.extend(["--top-ports", str(top_ports)])

    async def run(self, task: Task, ctx: RunContext) -> RawResult:
        """Execute Nmap via ProcessRunner and capture XML artifacts."""
        installed = self.check_installed()
        if not installed.installed:
            err = installed.error or "nmap binary not found or not executable"
            ctx.emit_output(f"[nmap] error: {err}")
            return RawResult(
                exit_code=127,
                stderr=err.encode("utf-8"),
                duration_seconds=0.0,
            )

        xml_filename = f"nmap_{task.id}.xml"
        xml_file = ctx.artifacts_dir / xml_filename

        # Ensure task uses the concrete artifact path
        task_with_xml = task.model_copy(update={"args": {**task.args, "xml_path": str(xml_file)}})
        cmd = self.build_command(task_with_xml)

        runner = ProcessRunner()
        proc_result = await runner.run(
            cmd,
            cwd=ctx.workspace_dir,
            timeout=ctx.timeout_seconds,
            on_line=ctx.emit_output,
            cancel_event=ctx.cancel_event,
        )

        artifacts: list[ArtifactRecord] = []
        xml_bytes = b""

        if xml_file.exists():
            try:
                xml_bytes = xml_file.read_bytes()
                sha256 = hashlib.sha256(xml_bytes).hexdigest()
                artifacts.append(
                    ArtifactRecord(
                        task_id=task.id,
                        engagement_id=task.engagement_id,
                        artifact_type="nmap_xml",
                        mime_type="application/xml",
                        path=f"artifacts/{xml_filename}",
                        size_bytes=len(xml_bytes),
                        sha256=sha256,
                        tool=self.name,
                        tool_version=installed.version or "unknown",
                        command_line=cmd,
                        created_at=ctx.clock.now(),
                    )
                )
            except OSError as exc:
                ctx.emit_output(f"[nmap] warning: failed to read XML artifact: {exc}")

        output_data = xml_bytes if xml_bytes else proc_result.stdout

        return RawResult(
            exit_code=proc_result.exit_code,
            stdout=output_data,
            stderr=proc_result.stderr,
            duration_seconds=proc_result.duration_seconds,
            timed_out=proc_result.timed_out,
            artifacts=artifacts,
        )

    def parse(self, raw: RawResult) -> list[Observation]:
        """Extract typed domain observations from raw Nmap execution result."""
        task_id = "unknown"
        engagement_id = "unknown"
        observed_at = None

        if raw.artifacts:
            art = raw.artifacts[0]
            task_id = art.task_id
            engagement_id = art.engagement_id
            observed_at = art.created_at

        # Check stdout if it contains Nmap XML
        xml_data: str | bytes = b""
        if raw.stdout and (b"<nmaprun" in raw.stdout or "<nmaprun" in str(raw.stdout)):
            xml_data = raw.stdout

        # Try parsing from artifact file on disk if stdout was not XML
        if not xml_data and raw.artifacts:
            art_path = Path(raw.artifacts[0].path)
            if art_path.exists():
                try:
                    xml_data = art_path.read_bytes()
                except OSError:
                    xml_data = b""

        if not xml_data:
            return []

        return parse_nmap_xml(
            xml_content=xml_data,
            task_id=task_id,
            engagement_id=engagement_id,
            observed_at=observed_at,
        )
