"""Application configuration loading and validation.

Configuration is assembled from three sources in ascending priority:

1. **Package defaults** – ``config/default.yaml`` embedded in the package.
2. **User config** – ``$NAYRAASTRA_HOME/config.yaml`` if it exists.
3. **Environment overrides** – variables prefixed ``NAYRAASTRA_`` with ``__``
   as the nesting delimiter (e.g. ``NAYRAASTRA_LOGGING__LEVEL=DEBUG``).

The result is a frozen :class:`AppConfig` Pydantic v2 model.  Schema errors
and invalid YAML both raise :class:`~nayraastra.core.errors.ConfigError`.

Dependency rule: ``core`` must not import from ``db``, ``cli``, or ``modules``.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from nayraastra.core.domain.types import Intrusiveness
from nayraastra.core.errors import ConfigError

# Backwards compatibility alias for Phase 0 callers
IntrusivenessLevel = Intrusiveness

# Circular-import note: ``core.paths`` imports nothing from ``core.config``,
# so a module-level import here is safe.  We keep it at module level to satisfy
# ruff PLC0415 and to make the dependency explicit.
from nayraastra.core.paths import get_home  # noqa: E402

# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class LoggingConfig(BaseModel, frozen=True):
    """Logging subsystem configuration."""

    level: str = "INFO"
    file_enabled: bool = True
    json_format: bool = False

    @field_validator("level", mode="before")
    @classmethod
    def _normalise_level(cls, v: Any) -> str:
        normalised = str(v).upper()
        if normalised not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"Invalid log level {v!r}. Choose from: {', '.join(sorted(_VALID_LOG_LEVELS))}"
            )
        return normalised


class DatabaseConfig(BaseModel, frozen=True):
    """SQLite database configuration."""

    filename: str = "nayraastra.db"
    wal: bool = True
    busy_timeout_ms: int = 5000

    @field_validator("busy_timeout_ms", mode="before")
    @classmethod
    def _positive_timeout(cls, v: Any) -> int:
        value = int(v)
        if value < 0:
            raise ValueError("busy_timeout_ms must be >= 0")
        return value


class ExecutionConfig(BaseModel, frozen=True):
    """Task execution constraints."""

    default_timeout_seconds: int = 300
    max_parallel_tasks: int = 4
    rate_limit_per_second: float = 10.0

    @field_validator("max_parallel_tasks", mode="before")
    @classmethod
    def _positive_parallel(cls, v: Any) -> int:
        value = int(v)
        if value < 1:
            raise ValueError("max_parallel_tasks must be >= 1")
        return value

    @field_validator("rate_limit_per_second", mode="before")
    @classmethod
    def _positive_rate(cls, v: Any) -> float:
        value = float(v)
        if value <= 0:
            raise ValueError("rate_limit_per_second must be > 0")
        return value


class SafetyConfig(BaseModel, frozen=True):
    """Safety and intrusiveness policy configuration."""

    max_intrusiveness: Intrusiveness = Intrusiveness.ACTIVE_SAFE
    disruptive_enabled: bool = False

    @model_validator(mode="after")
    def _disruptive_guard(self) -> SafetyConfig:
        if self.max_intrusiveness == Intrusiveness.DISRUPTIVE and not self.disruptive_enabled:
            raise ValueError(
                "max_intrusiveness=disruptive requires disruptive_enabled=true. "
                "Set this explicitly to confirm you understand the risk."
            )
        return self


class AdaptersConfig(BaseModel, frozen=True):
    """Adapter subsystem configuration."""

    fake_enabled: bool = False


# ---------------------------------------------------------------------------
# Root model
# ---------------------------------------------------------------------------


class AppConfig(BaseModel, frozen=True, extra="forbid"):
    """Root application configuration object."""

    logging: LoggingConfig = LoggingConfig()
    database: DatabaseConfig = DatabaseConfig()
    execution: ExecutionConfig = ExecutionConfig()
    safety: SafetyConfig = SafetyConfig()
    adapters: AdaptersConfig = AdaptersConfig()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENV_PREFIX = "NAYRAASTRA_"
_NEST_SEP = "__"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base*, returning a new dict."""
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _env_overrides() -> dict[str, Any]:
    """Build a nested dict from ``NAYRAASTRA_*`` environment variables.

    Only variables that contain ``__`` are treated as config overrides
    (e.g. ``NAYRAASTRA_LOGGING__LEVEL``).  Simple variables such as
    ``NAYRAASTRA_HOME`` are ignored here because they are not config keys.
    """
    overrides: dict[str, Any] = {}
    for key, raw_value in os.environ.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        without_prefix = key[len(_ENV_PREFIX) :]

        # Require at least one nesting delimiter so plain vars like
        # NAYRAASTRA_HOME are not injected into the config dict.
        if _NEST_SEP not in without_prefix:
            continue

        parts = without_prefix.lower().split(_NEST_SEP)

        # Coerce common scalars; leave the rest as strings for Pydantic.
        value: Any = raw_value
        if raw_value.lower() in {"true", "yes", "1"}:
            value = True
        elif raw_value.lower() in {"false", "no", "0"}:
            value = False
        elif raw_value.isdigit():
            value = int(raw_value)
        else:
            with contextlib.suppress(ValueError):
                value = float(raw_value)

        # Nest into dict.
        node = overrides
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    return overrides


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Load and parse a YAML file, returning a plain dict.

    Raises
    ------
    ConfigError
        On file read errors or YAML parse failures.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            f"Cannot read config file {path}: {exc}",
            details={"path": str(path)},
        ) from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(
            f"Invalid YAML in {path}: {exc}",
            details={"path": str(path)},
        ) from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(
            f"Config file {path} must contain a YAML mapping at the top level.",
            details={"path": str(path), "got_type": type(data).__name__},
        )
    return data


def _default_yaml_path() -> Path:
    """Return the path to the package-bundled default config."""
    return Path(__file__).parent.parent.parent.parent / "config" / "default.yaml"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(path: Path | None = None) -> AppConfig:
    """Load, merge, and validate the application configuration.

    Parameters
    ----------
    path:
        Explicit path to a user config YAML file.  If *None*, the loader
        looks for ``$NAYRAASTRA_HOME/config.yaml``.

    Returns
    -------
    AppConfig
        A frozen, validated configuration object.

    Raises
    ------
    ConfigError
        On YAML parse errors or Pydantic schema validation failures.
    """
    # 1. Package defaults.
    default_path = _default_yaml_path()
    merged: dict[str, Any] = _load_yaml_file(default_path) if default_path.exists() else {}

    # 2. User config (explicit path or home-relative).
    if path is not None:
        user_data = _load_yaml_file(path)
        merged = _deep_merge(merged, user_data)
    else:
        user_path = get_home() / "config.yaml"
        if user_path.exists():
            user_data = _load_yaml_file(user_path)
            merged = _deep_merge(merged, user_data)

    # 3. Environment variable overrides.
    merged = _deep_merge(merged, _env_overrides())

    # 4. Validate with Pydantic.
    try:
        return AppConfig.model_validate(merged)
    except PydanticValidationError as exc:
        raise ConfigError(
            f"Configuration validation failed: {exc}",
            details={"errors": exc.errors()},
        ) from exc
