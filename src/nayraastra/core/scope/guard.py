"""Scope enforcement guard for NAYRAASTRA.

Guarantees:
- Explicit out-of-scope (deny rules) always win over allow rules.
- Targets must match at least one in-scope rule; otherwise blocked.
- CIDR targets must be fully contained within in-scope ranges and have no overlap with deny rules.
- Wildcard domains (*.example.com) match subdomains at any depth, but never match the apex.
- When DNS resolution is performed, all resolved IPs must be allowed.
"""

from __future__ import annotations

import ipaddress

from pydantic import BaseModel, Field

from nayraastra.core.domain.models import ScopeEntry, Target
from nayraastra.core.domain.types import ScopeEntryKind, TargetKind
from nayraastra.core.ports import Resolver


class ScopeDecision(BaseModel, frozen=True, extra="forbid"):
    """Outcome of evaluating a target against engagement scope."""

    allowed: bool
    reason: str
    matched_rule: ScopeEntry | None = None
    violations: list[str] = Field(default_factory=list)


class StaticResolver:
    """Mock resolver for unit and integration testing."""

    def __init__(self, mapping: dict[str, list[str]] | None = None) -> None:
        self._mapping: dict[str, list[str]] = dict(mapping or {})

    def set_host(self, host: str, ips: list[str]) -> None:
        self._mapping[host.lower()] = list(ips)

    def resolve(self, hostname: str) -> list[str]:
        return self._mapping.get(hostname.lower(), [])


def _ip_in_network(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    net: ipaddress.IPv4Network | ipaddress.IPv6Network,
) -> bool:
    return ip.version == net.version and ip in net


def _network_contains(
    parent: ipaddress.IPv4Network | ipaddress.IPv6Network,
    child: ipaddress.IPv4Network | ipaddress.IPv6Network,
) -> bool:
    if isinstance(parent, ipaddress.IPv4Network) and isinstance(child, ipaddress.IPv4Network):
        return child.subnet_of(parent)
    if isinstance(parent, ipaddress.IPv6Network) and isinstance(child, ipaddress.IPv6Network):
        return child.subnet_of(parent)
    return False


def _networks_overlap(
    net1: ipaddress.IPv4Network | ipaddress.IPv6Network,
    net2: ipaddress.IPv4Network | ipaddress.IPv6Network,
) -> bool:
    if isinstance(net1, ipaddress.IPv4Network) and isinstance(net2, ipaddress.IPv4Network):
        return net1.overlaps(net2)
    if isinstance(net1, ipaddress.IPv6Network) and isinstance(net2, ipaddress.IPv6Network):
        return net1.overlaps(net2)
    return False


class ScopeGuard:
    """Evaluates targets against explicit scope entries."""

    def __init__(
        self,
        scope_entries: list[ScopeEntry],
        resolver: Resolver | None = None,
        fail_closed: bool = True,
    ) -> None:
        self.scope_entries = list(scope_entries)
        self.resolver = resolver
        self.fail_closed = fail_closed

        # Pre-parse entries for fast matching
        self._deny_entries = [e for e in self.scope_entries if not e.in_scope]
        self._allow_entries = [e for e in self.scope_entries if e.in_scope]

    def _match_domain(self, target_domain: str, entry: ScopeEntry) -> bool:
        t_domain = target_domain.lower()
        rule = entry.value.lower()

        if entry.kind == ScopeEntryKind.WILDCARD_DOMAIN or rule.startswith("*."):
            prefix = "*."
            apex = rule[len(prefix) :] if rule.startswith(prefix) else rule
            # Wildcard matches any sub-domain, but NOT the apex
            if t_domain == apex:
                return False
            return t_domain.endswith("." + apex)

        # Exact domain match
        return t_domain == rule

    def _check_ip_or_cidr(
        self,
        target_ip_or_net: ipaddress.IPv4Network
        | ipaddress.IPv6Network
        | ipaddress.IPv4Address
        | ipaddress.IPv6Address,
    ) -> tuple[bool, str, ScopeEntry | None]:
        is_net = isinstance(target_ip_or_net, ipaddress.IPv4Network | ipaddress.IPv6Network)

        # 1. Deny rules check first (out-of-scope always wins)
        for deny in self._deny_entries:
            if deny.kind in (ScopeEntryKind.IP, ScopeEntryKind.CIDR):
                try:
                    deny_net = ipaddress.ip_network(deny.value, strict=False)
                except ValueError:
                    continue

                if is_net:
                    if _networks_overlap(target_ip_or_net, deny_net):  # type: ignore[arg-type]
                        return False, f"Target CIDR overlaps out-of-scope rule {deny.value}", deny
                elif _ip_in_network(target_ip_or_net, deny_net):  # type: ignore[arg-type]
                    return False, f"Target IP matches out-of-scope rule {deny.value}", deny

        # 2. In-scope match required
        for allow in self._allow_entries:
            if allow.kind in (ScopeEntryKind.IP, ScopeEntryKind.CIDR):
                try:
                    allow_net = ipaddress.ip_network(allow.value, strict=False)
                except ValueError:
                    continue

                if is_net:
                    if _network_contains(allow_net, target_ip_or_net):  # type: ignore[arg-type]
                        return (
                            True,
                            f"Target CIDR fully contained in in-scope rule {allow.value}",
                            allow,
                        )
                elif _ip_in_network(target_ip_or_net, allow_net):  # type: ignore[arg-type]
                    return True, f"Target IP matches in-scope rule {allow.value}", allow

        return False, "Target IP/CIDR is not covered by any in-scope rule", None

    def check(
        self,
        target: Target,
        resolved_ips: list[str] | None = None,
    ) -> ScopeDecision:
        """Evaluate target against scope rules.

        Parameters
        ----------
        target:
            The normalized Target to inspect.
        resolved_ips:
            Optional pre-resolved IP addresses for hostname targets.
        """
        # --- IP Target ---
        if target.kind == TargetKind.IP:
            try:
                target_ip = ipaddress.ip_address(target.normalized)
            except ValueError:
                return ScopeDecision(
                    allowed=False,
                    reason=f"Corrupt normalized IP: {target.normalized}",
                    violations=["Invalid normalized IP"],
                )

            allowed, reason, rule = self._check_ip_or_cidr(target_ip)
            return ScopeDecision(
                allowed=allowed,
                reason=reason,
                matched_rule=rule,
                violations=[] if allowed else [reason],
            )

        # --- CIDR Target ---
        if target.kind == TargetKind.CIDR:
            try:
                target_net = ipaddress.ip_network(target.normalized, strict=True)
            except ValueError:
                return ScopeDecision(
                    allowed=False,
                    reason=f"Corrupt normalized CIDR: {target.normalized}",
                    violations=["Invalid normalized CIDR"],
                )

            allowed, reason, rule = self._check_ip_or_cidr(target_net)
            return ScopeDecision(
                allowed=allowed,
                reason=reason,
                matched_rule=rule,
                violations=[] if allowed else [reason],
            )

        # --- Domain or URL_HOST Target ---
        domain = target.normalized

        # 1. Deny rules for domain
        for deny in self._deny_entries:
            if deny.kind in (
                ScopeEntryKind.DOMAIN,
                ScopeEntryKind.WILDCARD_DOMAIN,
            ) and self._match_domain(domain, deny):
                return ScopeDecision(
                    allowed=False,
                    reason=f"Target domain matches out-of-scope rule {deny.value}",
                    matched_rule=deny,
                    violations=[f"Domain matches deny rule {deny.value}"],
                )

        # 2. Allow rules for domain
        matched_allow: ScopeEntry | None = None
        for allow in self._allow_entries:
            if allow.kind in (
                ScopeEntryKind.DOMAIN,
                ScopeEntryKind.WILDCARD_DOMAIN,
            ) and self._match_domain(domain, allow):
                matched_allow = allow
                break

        if not matched_allow:
            return ScopeDecision(
                allowed=False,
                reason="Target domain is not covered by any in-scope rule",
                violations=["Domain not in scope"],
            )

        # 3. DNS resolution check (if resolver or resolved_ips provided)
        ips_to_check: list[str] = []
        if resolved_ips is not None:
            ips_to_check = resolved_ips
        elif self.resolver is not None:
            try:
                ips_to_check = self.resolver.resolve(domain)
            except Exception as exc:
                if self.fail_closed:
                    return ScopeDecision(
                        allowed=False,
                        reason=f"DNS resolution failed for {domain} (fail_closed active): {exc}",
                        violations=[f"DNS resolution failure: {exc}"],
                    )
                ips_to_check = []

            if not ips_to_check and self.fail_closed:
                return ScopeDecision(
                    allowed=False,
                    reason=f"No IP addresses resolved for domain {domain} (fail_closed active)",
                    violations=["No resolved IPs"],
                )

        # Validate every resolved IP
        for ip_str in ips_to_check:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
            except ValueError:
                return ScopeDecision(
                    allowed=False,
                    reason=f"Resolved IP {ip_str!r} is malformed",
                    violations=[f"Malformed resolved IP: {ip_str}"],
                )

            ip_allowed, ip_reason, _ = self._check_ip_or_cidr(ip_obj)
            if not ip_allowed:
                return ScopeDecision(
                    allowed=False,
                    reason=f"Domain {domain} resolved to out-of-scope IP {ip_str} ({ip_reason})",
                    violations=[f"Resolved IP {ip_str} blocked: {ip_reason}"],
                )

        return ScopeDecision(
            allowed=True,
            reason=f"Target domain matches in-scope rule {matched_allow.value}",
            matched_rule=matched_allow,
            violations=[],
        )
