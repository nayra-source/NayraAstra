"""Target normalization and validation for NAYRAASTRA.

Strict deny-by-default validation preventing argument injection, path traversal,
and shell metacharacter manipulation.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

from nayraastra.core.domain.models import Target
from nayraastra.core.domain.types import TargetKind
from nayraastra.core.errors import ValidationFailure

# Shell metacharacters and forbidden characters for standard targets
_FORBIDDEN_CHARS = re.compile(r"[\s\x00-\x1f\x7f-\x9f&;|$\><`\\!*?\[\](){}\"']")

# Forbidden characters for URLs (allows ? and & in query string, but blocks command injection chars)
_FORBIDDEN_URL_CHARS = re.compile(r"[\s\x00-\x1f\x7f-\x9f;|$\><`\\!*\[\]{}\"']")

# Banned octal/hex IPv4 patterns like 010.0.0.1 or 0x7f.0.0.1
_IPV4_OCTAL_HEX = re.compile(r"(^|\.)(0\d+|0x[0-9a-fA-F]+)")


def _validate_label(label: str) -> None:
    if not label or len(label) > 63:
        raise ValidationFailure(
            f"DNS label length must be between 1 and 63 characters: {label!r}",
            details={"label": label},
        )
    if label.startswith("-") or label.endswith("-"):
        raise ValidationFailure(
            f"DNS label cannot start or end with a hyphen: {label!r}",
            details={"label": label},
        )
    if not re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", label):
        raise ValidationFailure(
            f"Invalid characters in DNS label: {label!r}",
            details={"label": label},
        )


def normalize_target(raw: str) -> Target:
    """Normalize and strictly validate a target string.

    Parameters
    ----------
    raw:
        Raw input string representing an IP, CIDR, hostname, or HTTP(S) URL.

    Returns
    -------
    Target
        A validated and normalized Target object.

    Raises
    ------
    ValidationFailure
        If raw target violates any security or structural constraints.
    """
    if not raw:
        raise ValidationFailure("Target cannot be empty.")

    if len(raw) > 253:
        raise ValidationFailure(
            f"Target length exceeds maximum of 253 characters ({len(raw)} chars).",
            details={"length": len(raw)},
        )

    # Argument injection defence: target must never start with a hyphen
    if raw.startswith("-"):
        raise ValidationFailure(
            f"Target cannot start with a hyphen (argument injection prevention): {raw!r}",
            details={"target": raw},
        )

    # URL handling: extract host, port, path
    if raw.startswith("http://") or raw.startswith("https://"):
        if _FORBIDDEN_URL_CHARS.search(raw):
            raise ValidationFailure(
                f"Target contains forbidden characters or whitespace: {raw!r}",
                details={"target": raw},
            )
        try:
            parsed = urlparse(raw)
        except Exception as exc:
            raise ValidationFailure(f"Invalid URL target: {exc}", details={"target": raw}) from exc

        if not parsed.hostname:
            raise ValidationFailure("URL has no valid hostname.", details={"target": raw})

        host_target = normalize_target(parsed.hostname)
        return Target(
            raw=raw,
            normalized=host_target.normalized,
            kind=TargetKind.URL_HOST,
            port=parsed.port or (443 if parsed.scheme == "https" else 80),
            path=parsed.path or "/",
            metadata={"scheme": parsed.scheme, "url": raw},
        )

    # Reject whitespace, control characters, and shell metacharacters for non-URL targets
    if _FORBIDDEN_CHARS.search(raw):
        raise ValidationFailure(
            f"Target contains forbidden characters or whitespace: {raw!r}",
            details={"target": raw},
        )

    # Short-form or non-canonical IPv4 forms (e.g. 127.1, 10.1, 010.0.0.1)
    dot_parts = raw.split(".")
    if len(dot_parts) > 1 and all(p.isdigit() for p in dot_parts):
        if len(dot_parts) != 4:
            raise ValidationFailure(
                f"Short-form IPv4 addresses are forbidden: {raw!r}",
                details={"target": raw},
            )
        if any(int(p) > 255 for p in dot_parts):
            raise ValidationFailure(
                f"IPv4 octet exceeds 255: {raw!r}",
                details={"target": raw},
            )
        if any(len(p) > 1 and p.startswith("0") for p in dot_parts):
            raise ValidationFailure(
                f"IPv4 addresses with leading zeros are forbidden: {raw!r}",
                details={"target": raw},
            )

    # CIDR handling
    if "/" in raw:
        parts = raw.split("/")
        if len(parts) != 2:
            raise ValidationFailure(f"Invalid CIDR syntax: {raw!r}", details={"target": raw})

        # Reject IPv4 octal/hex in CIDR prefix
        if _IPV4_OCTAL_HEX.search(parts[0]):
            raise ValidationFailure(
                f"IPv4 addresses with leading zeros/octal/hex are forbidden: {raw!r}",
                details={"target": raw},
            )

        try:
            net = ipaddress.ip_network(raw, strict=True)
            return Target(
                raw=raw,
                normalized=str(net),
                kind=TargetKind.CIDR,
            )
        except ValueError as exc:
            raise ValidationFailure(
                f"Invalid strict CIDR (host bits must be 0): {exc}",
                details={"target": raw},
            ) from exc

    # IPv6 zone IDs rejection (%eth0)
    if "%" in raw:
        raise ValidationFailure(
            f"IPv6 zone IDs are not permitted: {raw!r}", details={"target": raw}
        )

    # IPv4 / IPv6 Single Address
    # Reject leading zeros / octal / hex forms for IPv4
    if _IPV4_OCTAL_HEX.search(raw):
        raise ValidationFailure(
            f"IPv4 addresses with leading zeros/octal/hex are forbidden: {raw!r}",
            details={"target": raw},
        )

    try:
        ip = ipaddress.ip_address(raw)
        return Target(
            raw=raw,
            normalized=str(ip),
            kind=TargetKind.IP,
        )
    except ValueError:
        pass  # Not an IP address, proceed to hostname validation

    # Hostname / FQDN handling
    hostname = raw.lower()
    # Strip a single trailing dot if present
    if hostname.endswith("."):
        hostname = hostname[:-1]

    if not hostname:
        raise ValidationFailure("Hostname cannot be empty.", details={"target": raw})

    # Convert IDN (Internationalized Domain Names) to Punycode
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except Exception as exc:
        raise ValidationFailure(
            f"Failed to encode hostname to IDNA ASCII: {exc}", details={"target": raw}
        ) from exc

    labels = ascii_hostname.split(".")
    if len(labels) > 1 and labels[-1].isdigit():
        raise ValidationFailure(
            f"Domain name cannot have an all-numeric TLD: {raw!r}",
            details={"target": raw},
        )
    for label in labels:
        _validate_label(label)

    return Target(
        raw=raw,
        normalized=ascii_hostname,
        kind=TargetKind.DOMAIN,
    )
