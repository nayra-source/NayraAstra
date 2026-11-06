"""Robust XML output parser for Nmap scan results."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from nayraastra.core.domain.models import Observation

logger = logging.getLogger("nayraastra.adapters.nmap.parser")


def parse_nmap_xml(
    xml_content: str | bytes,
    task_id: str,
    engagement_id: str,
    observed_at: datetime | None = None,
) -> list[Observation]:
    """Parse Nmap XML output into typed domain Observation records.

    Parameters
    ----------
    xml_content
        String or raw bytes of Nmap XML output.
    task_id
        Associated task identifier.
    engagement_id
        Associated engagement identifier.
    observed_at
        Timestamp to assign to observations (defaults to current UTC).

    Returns
    -------
    list[Observation]
        Parsed observations for hosts, open ports, services, and OS matches.
    """
    observations: list[Observation] = []
    ts = observed_at or datetime.now(UTC)

    if not xml_content:
        return observations

    try:
        if isinstance(xml_content, str):
            root = ET.fromstring(xml_content)  # noqa: S314
        else:
            root = ET.fromstring(xml_content.decode("utf-8", errors="replace"))  # noqa: S314
    except ET.ParseError as exc:
        logger.warning("Failed to parse Nmap XML for task %s: %s", task_id, exc)
        return observations

    for host_el in root.findall("host"):
        # 1. Host addresses & vendor
        ip_addr: str | None = None
        addrtype: str = "ipv4"
        mac_addr: str | None = None
        mac_vendor: str | None = None

        for addr_el in host_el.findall("address"):
            atype = addr_el.get("addrtype", "")
            if atype in ("ipv4", "ipv6") and ip_addr is None:
                ip_addr = addr_el.get("addr")
                addrtype = atype
            elif atype == "mac":
                mac_addr = addr_el.get("addr")
                mac_vendor = addr_el.get("vendor")

        if not ip_addr:
            continue

        # Hostnames
        hostnames: list[str] = [
            h.get("name", "") for h in host_el.findall("hostnames/hostname") if h.get("name")
        ]

        # Host status
        status_el = host_el.find("status")
        state = status_el.get("state", "unknown") if status_el is not None else "unknown"
        reason = status_el.get("reason", "") if status_el is not None else ""

        if state == "up":
            host_val: dict[str, object] = {
                "address": ip_addr,
                "addrtype": addrtype,
                "state": "up",
                "reason": reason,
                "hostnames": hostnames,
            }
            if mac_addr:
                host_val["mac"] = mac_addr
            if mac_vendor:
                host_val["vendor"] = mac_vendor

            observations.append(
                Observation(
                    task_id=task_id,
                    engagement_id=engagement_id,
                    observation_key="host_up",
                    value=host_val,
                    observed_at=ts,
                )
            )
        elif state == "down":
            observations.append(
                Observation(
                    task_id=task_id,
                    engagement_id=engagement_id,
                    observation_key="host_down",
                    value={
                        "address": ip_addr,
                        "addrtype": addrtype,
                        "state": "down",
                        "reason": reason,
                    },
                    observed_at=ts,
                )
            )

        # 2. Port and service discovery
        for port_el in host_el.findall("ports/port"):
            proto = port_el.get("protocol", "tcp")
            try:
                port_id = int(port_el.get("portid", "0"))
            except ValueError:
                continue

            state_el = port_el.find("state")
            port_state = state_el.get("state", "unknown") if state_el is not None else "unknown"
            port_reason = state_el.get("reason", "") if state_el is not None else ""

            # Port status observation
            obs_key = "open_port" if port_state == "open" else f"port_{port_state}"
            observations.append(
                Observation(
                    task_id=task_id,
                    engagement_id=engagement_id,
                    observation_key=obs_key,
                    value={
                        "address": ip_addr,
                        "port": port_id,
                        "protocol": proto,
                        "state": port_state,
                        "reason": port_reason,
                    },
                    observed_at=ts,
                )
            )

            # Service details observation
            service_el = port_el.find("service")
            if service_el is not None:
                s_name = service_el.get("name", "")
                s_prod = service_el.get("product")
                s_ver = service_el.get("version")
                s_extra = service_el.get("extrainfo")
                s_cpes = [c.text.strip() for c in service_el.findall("cpe") if c.text]
                s_conf = service_el.get("conf", "3")
                s_method = service_el.get("method", "table")

                svc_val: dict[str, object] = {
                    "address": ip_addr,
                    "port": port_id,
                    "protocol": proto,
                    "service": s_name,
                    "method": s_method,
                    "confidence": s_conf,
                }
                if s_prod:
                    svc_val["product"] = s_prod
                if s_ver:
                    svc_val["version"] = s_ver
                if s_extra:
                    svc_val["extrainfo"] = s_extra
                if s_cpes:
                    svc_val["cpe"] = s_cpes

                observations.append(
                    Observation(
                        task_id=task_id,
                        engagement_id=engagement_id,
                        observation_key="service_detected",
                        value=svc_val,
                        observed_at=ts,
                    )
                )

            # Script output observations
            for script_el in port_el.findall("script"):
                s_id = script_el.get("id", "")
                s_out = script_el.get("output", "")
                if s_id:
                    observations.append(
                        Observation(
                            task_id=task_id,
                            engagement_id=engagement_id,
                            observation_key="script_output",
                            value={
                                "address": ip_addr,
                                "port": port_id,
                                "protocol": proto,
                                "script_id": s_id,
                                "output": s_out,
                            },
                            observed_at=ts,
                        )
                    )

        # 3. OS detection observations
        for osmatch_el in host_el.findall("os/osmatch"):
            os_name = osmatch_el.get("name", "")
            try:
                accuracy = int(osmatch_el.get("accuracy", "0"))
            except ValueError:
                accuracy = 0
            os_cpes = [c.text.strip() for c in osmatch_el.findall("osclass/cpe") if c.text]

            observations.append(
                Observation(
                    task_id=task_id,
                    engagement_id=engagement_id,
                    observation_key="os_match",
                    value={
                        "address": ip_addr,
                        "name": os_name,
                        "accuracy": accuracy,
                        "cpe": os_cpes,
                    },
                    observed_at=ts,
                )
            )

    return observations
