"""Unit and property-based tests for target normalization and scope guard."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nayraastra.core.domain.models import ScopeEntry
from nayraastra.core.domain.types import ScopeEntryKind, TargetKind
from nayraastra.core.errors import ValidationFailure
from nayraastra.core.scope.guard import ScopeGuard, StaticResolver
from nayraastra.core.scope.normalize import normalize_target


@pytest.mark.unit
class TestTargetNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected_normalized", "expected_kind"),
        [
            ("192.168.1.1", "192.168.1.1", TargetKind.IP),
            ("::1", "::1", TargetKind.IP),
            ("2001:db8::1", "2001:db8::1", TargetKind.IP),
            ("10.0.0.0/8", "10.0.0.0/8", TargetKind.CIDR),
            ("192.168.1.0/24", "192.168.1.0/24", TargetKind.CIDR),
            ("example.com", "example.com", TargetKind.DOMAIN),
            ("EXAMPLE.COM", "example.com", TargetKind.DOMAIN),
            ("sub.example.com.", "sub.example.com", TargetKind.DOMAIN),
            ("bücher.example", "xn--bcher-kva.example", TargetKind.DOMAIN),
            ("http://api.example.com", "api.example.com", TargetKind.URL_HOST),
            ("https://target.corp:8443/test/path", "target.corp", TargetKind.URL_HOST),
        ],
    )
    def test_valid_targets(
        self, raw: str, expected_normalized: str, expected_kind: TargetKind
    ) -> None:
        t = normalize_target(raw)
        assert t.normalized == expected_normalized
        assert t.kind == expected_kind

    @pytest.mark.parametrize(
        "invalid_raw",
        [
            "",  # empty
            "   ",  # whitespace
            "-oX",  # argument injection prevention
            "--script=vuln",  # argument injection
            "-sS",
            "10.0.0.1/8",  # host bits set in strict CIDR
            "192.168.1.5/24",  # host bits set
            "010.0.0.1",  # octal/leading zero IPv4
            "0x7f.0.0.1",  # hex IPv4
            "127.1",  # short form IPv4
            "fe80::1%eth0",  # IPv6 zone ID
            "target;rm -rf /",  # shell injection character
            "target|cat /etc/passwd",
            "target&whoami",
            "target`id`",
            "target$(id)",
            "target<input",
            "target>output",
            "a" * 254,  # exceeds 253 chars
            "-badlabel.com",  # label starts with hyphen
            "badlabel-.com",  # label ends with hyphen
            "label with spaces.com",
        ],
    )
    def test_invalid_targets_rejected(self, invalid_raw: str) -> None:
        with pytest.raises(ValidationFailure):
            normalize_target(invalid_raw)

    def test_url_metadata_extraction(self) -> None:
        t = normalize_target("https://secure.lab.test:9000/app/login?user=admin")
        assert t.kind == TargetKind.URL_HOST
        assert t.normalized == "secure.lab.test"
        assert t.port == 9000
        assert t.path == "/app/login"
        assert t.metadata["scheme"] == "https"

    @given(
        st.sampled_from(
            [
                "10.0.0.1",
                "172.16.0.5",
                "192.168.1.100",
                "2001:db8::1",
                "10.0.0.0/24",
                "172.16.0.0/12",
                "corp.example.com",
                "api.v1.sub.test.org",
                "xn--bcher-kva.de",
            ]
        )
    )
    def test_normalization_idempotent_hypothesis(self, raw: str) -> None:
        t1 = normalize_target(raw)
        t2 = normalize_target(t1.normalized)
        assert t1.normalized == t2.normalized
        assert t1.kind == t2.kind


@pytest.mark.unit
class TestScopeGuard:
    def _make_entry(self, value: str, kind: ScopeEntryKind, in_scope: bool = True) -> ScopeEntry:
        return ScopeEntry(
            id=1,
            engagement_id="eng-1",
            kind=kind,
            value=value,
            in_scope=in_scope,
            created_at=datetime.now(UTC),
        )

    def test_out_of_scope_always_vetoes_in_scope(self) -> None:
        entries = [
            self._make_entry("10.0.0.0/8", ScopeEntryKind.CIDR, in_scope=True),
            self._make_entry("10.10.10.0/24", ScopeEntryKind.CIDR, in_scope=False),
        ]
        guard = ScopeGuard(entries)

        # 10.1.1.1 is inside /8 and not in /24 deny -> ALLOWED
        res1 = guard.check(normalize_target("10.1.1.1"))
        assert res1.allowed

        # 10.10.10.5 is inside /8 BUT inside /24 deny -> BLOCKED
        res2 = guard.check(normalize_target("10.10.10.5"))
        assert not res2.allowed
        assert "overlaps out-of-scope" in res2.reason or "out-of-scope rule" in res2.reason

    def test_cidr_target_containment(self) -> None:
        entries = [
            self._make_entry("192.168.0.0/16", ScopeEntryKind.CIDR, in_scope=True),
            self._make_entry("192.168.50.0/24", ScopeEntryKind.CIDR, in_scope=False),
        ]
        guard = ScopeGuard(entries)

        # Subnet fully contained in allow and no overlap with deny
        assert guard.check(normalize_target("192.168.10.0/24")).allowed

        # Subnet overlapping deny rule
        assert not guard.check(normalize_target("192.168.50.0/26")).allowed

        # Subnet wider than allow rule -> NOT fully contained
        assert not guard.check(normalize_target("192.0.0.0/8")).allowed

    def test_wildcard_domain_matching(self) -> None:
        entries = [
            self._make_entry("*.example.com", ScopeEntryKind.WILDCARD_DOMAIN, in_scope=True),
        ]
        guard = ScopeGuard(entries)

        # Subdomains match
        assert guard.check(normalize_target("sub.example.com")).allowed
        assert guard.check(normalize_target("deep.sub.example.com")).allowed

        # Apex domain must NOT match wildcard rule
        assert not guard.check(normalize_target("example.com")).allowed

        # Different domain
        assert not guard.check(normalize_target("other.com")).allowed

    def test_dns_rebinding_ip_check(self) -> None:
        resolver = StaticResolver(
            {
                "good.example.com": ["10.0.0.5"],
                "evil.example.com": ["192.168.1.1"],  # Resolves to out-of-scope IP
            }
        )
        entries = [
            self._make_entry("*.example.com", ScopeEntryKind.WILDCARD_DOMAIN, in_scope=True),
            self._make_entry("10.0.0.0/24", ScopeEntryKind.CIDR, in_scope=True),
            self._make_entry("192.168.1.0/24", ScopeEntryKind.CIDR, in_scope=False),
        ]
        guard = ScopeGuard(entries, resolver=resolver)

        # In-scope name -> in-scope IP -> allowed
        assert guard.check(normalize_target("good.example.com")).allowed

        # In-scope name -> out-of-scope IP -> blocked!
        decision = guard.check(normalize_target("evil.example.com"))
        assert not decision.allowed
        assert any(
            "blocked" in v.lower() or "out-of-scope" in v.lower() for v in decision.violations
        )

    def test_resolver_fail_closed(self) -> None:
        resolver = StaticResolver({})
        entries = [
            self._make_entry("unknown.example.com", ScopeEntryKind.DOMAIN, in_scope=True),
        ]
        guard = ScopeGuard(entries, resolver=resolver, fail_closed=True)
        decision = guard.check(normalize_target("unknown.example.com"))
        assert not decision.allowed
        assert "fail_closed" in decision.reason
