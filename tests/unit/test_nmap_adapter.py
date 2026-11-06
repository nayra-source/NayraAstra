"""Unit tests for NmapAdapter, command construction, and XML parsing."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nayraastra.adapters.base import RawResult, RunContext
from nayraastra.adapters.nmap import NmapAdapter, parse_nmap_xml
from nayraastra.core.domain.models import Target, Task
from nayraastra.core.domain.time_id import FrozenClock
from nayraastra.core.domain.types import Capability, Intrusiveness, TargetKind

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "nmap"


def _make_task(
    capability: Capability = Capability.PORT_SCAN,
    target_str: str = "192.168.1.1",
    args: dict[str, object] | None = None,
) -> Task:
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    return Task(
        id="task-test-nmap-1",
        engagement_id="eng-test-1",
        module_name=capability.value,
        adapter_name="nmap",
        capability=capability,
        target=Target(
            raw=target_str,
            normalized=target_str,
            kind=TargetKind.IP,
        ),
        intrusiveness=Intrusiveness.ACTIVE_SAFE,
        args=args or {},
        created_at=now,
    )


@pytest.mark.unit
class TestNmapCheckInstalled:
    def test_missing_binary_returns_not_installed(self) -> None:
        adapter = NmapAdapter()
        with patch("shutil.which", return_value=None):
            status = adapter.check_installed()
            assert not status.installed
            assert "not found in PATH" in str(status.error)

    def test_installed_binary_parses_version(self) -> None:
        adapter = NmapAdapter()
        mock_output = "Nmap version 7.94SVN ( https://nmap.org )\nPlatform: aarch64-apple-darwin\n"
        with (
            patch("shutil.which", return_value="/usr/local/bin/nmap"),
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=0, stdout=mock_output),
            ),
        ):
            status = adapter.check_installed()
            assert status.installed
            assert status.path == "/usr/local/bin/nmap"
            assert status.version == "7.94SVN"

    def test_different_version_formats(self) -> None:
        adapter = NmapAdapter(binary_path="/opt/bin/nmap")
        cases = [
            ("Nmap version 7.92\n", "7.92"),
            ("Nmap version 7.80BETA1 ( https://nmap.org )", "7.80BETA1"),
            ("Nmap version 6.40 ( http://nmap.org )", "6.40"),
        ]
        for stdout, expected_ver in cases:
            with patch(
                "subprocess.run",
                return_value=MagicMock(returncode=0, stdout=stdout),
            ):
                status = adapter.check_installed()
                assert status.installed
                assert status.version == expected_ver

    def test_nonzero_exit_code_returns_error(self) -> None:
        adapter = NmapAdapter()
        with (
            patch("shutil.which", return_value="/usr/bin/nmap"),
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=1, stdout="", stderr="Permission denied"),
            ),
        ):
            status = adapter.check_installed()
            assert not status.installed
            assert "non-zero exit code" in str(status.error)

    def test_exception_handling_during_version_check(self) -> None:
        adapter = NmapAdapter()
        with (
            patch("shutil.which", return_value="/usr/bin/nmap"),
            patch("subprocess.run", side_effect=OSError("Exec format error")),
        ):
            status = adapter.check_installed()
            assert not status.installed
            assert "Exec format error" in str(status.error)


@pytest.mark.unit
class TestNmapBuildCommand:
    def test_host_discovery_command(self) -> None:
        adapter = NmapAdapter()
        task = _make_task(Capability.HOST_DISCOVERY, "10.0.0.0/24")
        cmd = adapter.build_command(task)

        assert cmd[0] == "nmap"
        assert "-sn" in cmd
        assert "-oX" in cmd
        assert cmd[-2] == "--"
        assert cmd[-1] == "10.0.0.0/24"

    def test_port_scan_default_top_ports(self) -> None:
        adapter = NmapAdapter()
        task = _make_task(Capability.PORT_SCAN, "192.168.1.50")
        cmd = adapter.build_command(task)

        assert cmd[0] == "nmap"
        assert "-sS" in cmd
        assert "--top-ports" in cmd
        top_idx = cmd.index("--top-ports")
        assert cmd[top_idx + 1] == "100"
        assert "-oX" in cmd
        assert cmd[-2] == "--"
        assert cmd[-1] == "192.168.1.50"

    def test_port_scan_explicit_ports(self) -> None:
        adapter = NmapAdapter()
        task = _make_task(
            Capability.PORT_SCAN,
            "192.168.1.50",
            args={"ports": "22,80,443,8000-8080", "scan_type": "-sT"},
        )
        cmd = adapter.build_command(task)

        assert "-sT" in cmd
        assert "-p" in cmd
        assert cmd[cmd.index("-p") + 1] == "22,80,443,8000-8080"
        assert "--top-ports" not in cmd

    def test_service_detection_command(self) -> None:
        adapter = NmapAdapter()
        task = _make_task(
            Capability.SERVICE_DETECT,
            "192.168.1.1",
            args={"timing": "-T4", "xml_path": "artifacts/custom.xml"},
        )
        cmd = adapter.build_command(task)

        assert "-sV" in cmd
        assert "-T4" in cmd
        assert cmd[cmd.index("-oX") + 1] == "artifacts/custom.xml"
        assert cmd[-2] == "--"
        assert cmd[-1] == "192.168.1.1"

    def test_target_argument_injection_prevented_by_separator(self) -> None:
        adapter = NmapAdapter()
        task = _make_task(Capability.PORT_SCAN, "target.corp")
        cmd = adapter.build_command(task)

        # Target must always be the final element, immediately preceded by '--'
        assert cmd[-2] == "--"
        assert cmd[-1] == "target.corp"


@pytest.mark.unit
class TestNmapXmlParsing:
    def test_parse_sample_run_fixture(self) -> None:
        xml_path = _FIXTURES_DIR / "sample_run.xml"
        assert xml_path.exists(), f"Fixture missing at {xml_path}"

        observations = parse_nmap_xml(
            xml_content=xml_path.read_bytes(),
            task_id="t-sample",
            engagement_id="eng-sample",
        )

        assert len(observations) > 0

        # Verify host_up observation
        host_up_obs = [o for o in observations if o.observation_key == "host_up"]
        assert len(host_up_obs) == 1
        h = host_up_obs[0]
        assert h.value["address"] == "192.168.1.1"
        assert h.value["mac"] == "00:11:22:33:44:55"
        assert h.value["vendor"] == "Cisco Systems"
        assert "router.local" in h.value["hostnames"]  # type: ignore[operator]
        assert "gw.internal" in h.value["hostnames"]  # type: ignore[operator]

        # Verify host_down observation
        host_down_obs = [o for o in observations if o.observation_key == "host_down"]
        assert len(host_down_obs) == 1
        assert host_down_obs[0].value["address"] == "192.168.1.2"

        # Verify open_port observations (22, 80, 443 open)
        open_ports = [o for o in observations if o.observation_key == "open_port"]
        open_port_ids = [o.value["port"] for o in open_ports]
        assert 22 in open_port_ids
        assert 80 in open_port_ids
        assert 443 in open_port_ids

        # Verify closed and filtered ports
        closed_ports = [o for o in observations if o.observation_key == "port_closed"]
        assert any(o.value["port"] == 21 for o in closed_ports)

        filtered_ports = [o for o in observations if o.observation_key == "port_filtered"]
        assert any(o.value["port"] == 3389 for o in filtered_ports)

        # Verify service_detected observations
        services = [o for o in observations if o.observation_key == "service_detected"]
        ssh_svc = next((s for s in services if s.value["port"] == 22), None)
        assert ssh_svc is not None
        assert ssh_svc.value["service"] == "ssh"
        assert "OpenSSH" in str(ssh_svc.value.get("product"))
        assert "cpe:/a:openbsd:openssh:8.9p1" in ssh_svc.value["cpe"]  # type: ignore[operator]

        http_svc = next((s for s in services if s.value["port"] == 80), None)
        assert http_svc is not None
        assert http_svc.value["service"] == "http"
        assert http_svc.value["product"] == "nginx"

        # Verify script_output observation
        scripts = [o for o in observations if o.observation_key == "script_output"]
        assert len(scripts) >= 1
        title_script = next((s for s in scripts if s.value["script_id"] == "http-title"), None)
        assert title_script is not None
        assert "Router Admin Console" in str(title_script.value["output"])

        # Verify os_match observation
        os_matches = [o for o in observations if o.observation_key == "os_match"]
        assert len(os_matches) == 1
        assert "Linux" in str(os_matches[0].value["name"])
        assert os_matches[0].value["accuracy"] == 96

    def test_parse_single_host_fixture(self) -> None:
        xml_path = _FIXTURES_DIR / "single_host_ssh_http.xml"
        observations = parse_nmap_xml(
            xml_content=xml_path.read_text(),
            task_id="t-single",
            engagement_id="eng-single",
        )

        assert any(
            o.observation_key == "host_up" and o.value["address"] == "10.0.0.15"
            for o in observations
        )
        ports = [o.value["port"] for o in observations if o.observation_key == "open_port"]
        assert 22 in ports
        assert 80 in ports

    def test_parse_host_down_fixture(self) -> None:
        xml_path = _FIXTURES_DIR / "host_down.xml"
        observations = parse_nmap_xml(
            xml_content=xml_path.read_bytes(),
            task_id="t-down",
            engagement_id="eng-down",
        )
        assert len(observations) == 1
        assert observations[0].observation_key == "host_down"
        assert observations[0].value["address"] == "10.0.0.99"

    def test_parse_empty_fixture(self) -> None:
        xml_path = _FIXTURES_DIR / "empty_run.xml"
        observations = parse_nmap_xml(
            xml_content=xml_path.read_bytes(),
            task_id="t-empty",
            engagement_id="eng-empty",
        )
        assert observations == []

    def test_parse_malformed_xml_does_not_crash(self) -> None:
        xml_path = _FIXTURES_DIR / "malformed.xml"
        observations = parse_nmap_xml(
            xml_content=xml_path.read_bytes(),
            task_id="t-bad",
            engagement_id="eng-bad",
        )
        assert observations == []

    def test_adapter_parse_from_raw_result_stdout(self) -> None:
        adapter = NmapAdapter()
        xml_data = (_FIXTURES_DIR / "single_host_ssh_http.xml").read_bytes()
        raw = RawResult(
            exit_code=0,
            stdout=xml_data,
        )
        observations = adapter.parse(raw)
        assert len(observations) > 0
        assert any(o.observation_key == "open_port" for o in observations)


@pytest.mark.unit
class TestNmapAdapterRunAndEstimate:
    def test_estimate_scales_by_capability(self) -> None:
        adapter = NmapAdapter()
        t_disc = _make_task(Capability.HOST_DISCOVERY)
        t_port = _make_task(Capability.PORT_SCAN)
        t_svc = _make_task(Capability.SERVICE_DETECT)

        assert (
            adapter.estimate(t_disc).estimated_seconds < adapter.estimate(t_port).estimated_seconds
        )
        assert (
            adapter.estimate(t_port).estimated_seconds < adapter.estimate(t_svc).estimated_seconds
        )

    def test_run_missing_nmap_returns_code_127(self, tmp_path: Path) -> None:
        async def _test() -> None:
            adapter = NmapAdapter()
            task = _make_task()
            clock = FrozenClock(datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC))
            emitted: list[str] = []

            ctx = RunContext(
                workspace_dir=tmp_path,
                artifacts_dir=tmp_path / "artifacts",
                clock=clock,
                emit_output=emitted.append,
            )

            with patch.object(
                adapter,
                "check_installed",
                return_value=MagicMock(installed=False, error="nmap not found"),
            ):
                res = await adapter.run(task, ctx)
                assert res.exit_code == 127
                assert any("nmap" in line for line in emitted)

        asyncio.run(_test())

    def test_run_executes_and_captures_artifact(self, tmp_path: Path) -> None:
        async def _test() -> None:
            adapter = NmapAdapter(binary_path="/usr/bin/nmap")
            task = _make_task(Capability.PORT_SCAN, "10.0.0.1")
            artifacts_dir = tmp_path / "artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            clock = FrozenClock(datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC))
            emitted: list[str] = []

            ctx = RunContext(
                workspace_dir=tmp_path,
                artifacts_dir=artifacts_dir,
                clock=clock,
                emit_output=emitted.append,
            )

            sample_xml = (_FIXTURES_DIR / "single_host_ssh_http.xml").read_bytes()
            xml_file = artifacts_dir / f"nmap_{task.id}.xml"

            # Mock ProcessRunner: simulate nmap creating the xml file during execution
            async def _fake_run(*args: object, **kwargs: object) -> MagicMock:
                xml_file.write_bytes(sample_xml)
                return MagicMock(
                    exit_code=0,
                    stdout=b"Starting Nmap 7.94...\nNmap done: 1 IP address scanned in 2.0 seconds\n",
                    stderr=b"",
                    duration_seconds=1.5,
                    timed_out=False,
                )

            with (
                patch.object(
                    adapter,
                    "check_installed",
                    return_value=MagicMock(installed=True, version="7.94"),
                ),
                patch("nayraastra.adapters.nmap.adapter.ProcessRunner.run", side_effect=_fake_run),
            ):
                res = await adapter.run(task, ctx)
                assert res.exit_code == 0
                assert len(res.artifacts) == 1
                art = res.artifacts[0]
                assert art.tool == "nmap"
                assert art.tool_version == "7.94"
                assert art.mime_type == "application/xml"
                assert art.size_bytes == len(sample_xml)
                assert art.sha256 != ""

                # Now verify parse() on this result extracts observations
                observations = adapter.parse(res)
                assert len(observations) >= 3
                keys = [o.observation_key for o in observations]
                assert "host_up" in keys
                assert "open_port" in keys
                assert "service_detected" in keys

        asyncio.run(_test())
