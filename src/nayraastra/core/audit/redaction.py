"""Audit payload redaction and data sanitization."""

from __future__ import annotations

import re
from typing import Any

_SENSITIVE_KEY_RE = re.compile(r"(password|secret|token|key|credential)", re.IGNORECASE)
_MAX_VALUE_LENGTH = 1000
_REDACTED_PLACEHOLDER = "***REDACTED***"


def redact_data(data: Any, max_len: int = _MAX_VALUE_LENGTH) -> Any:
    """Recursively redact sensitive keys and truncate oversize values."""
    if isinstance(data, dict):
        cleaned: dict[str, Any] = {}
        for k, v in data.items():
            if _SENSITIVE_KEY_RE.search(str(k)):
                cleaned[str(k)] = _REDACTED_PLACEHOLDER
            else:
                cleaned[str(k)] = redact_data(v, max_len=max_len)
        return cleaned

    if isinstance(data, list | tuple):
        return [redact_data(item, max_len=max_len) for item in data]

    if isinstance(data, str):
        if len(data) > max_len:
            return data[:max_len] + f"... [truncated {len(data) - max_len} chars]"
        return data

    return data
