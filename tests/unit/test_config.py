"""Unit tests for nayraastra.core.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from nayraastra.core.config import AppConfig, IntrusivenessLevel, load_config
from nayraastra.core.errors import ConfigError


@pytest.mark.unit
class TestDefaults:
    def test_loads_without_user_config(self, fake_home: Path) -> None:
        cfg = load_config()
        assert isinstance(cfg, AppConfig)

    def test_default_log_level(self, fake_home: Path) -> None:
        cfg = load_config()
        assert cfg.logging.level == "INFO"

    def test_default_wal_enabled(self, fake_home: Path) -> None:
        cfg = load_config()
        assert cfg.database.wal is True

    def test_default_max_intrusiveness(self, fake_home: Path) -> None:
        cfg = load_config()
        assert cfg.safety.max_intrusiveness == IntrusivenessLevel.ACTIVE_SAFE

    def test_config_is_frozen(self, fake_home: Path) -> None:
        cfg = load_config()
        with pytest.raises(Exception):  # noqa: B017
            cfg.logging = cfg.logging  # type: ignore[misc]


@pytest.mark.unit
class TestUserOverride:
    def test_user_config_overrides_level(self, fake_home: Path) -> None:
        user_cfg = fake_home / "config.yaml"
        user_cfg.write_text("logging:\n  level: DEBUG\n")
        cfg = load_config()
        assert cfg.logging.level == "DEBUG"

    def test_user_config_partial_override(self, fake_home: Path) -> None:
        user_cfg = fake_home / "config.yaml"
        user_cfg.write_text("database:\n  busy_timeout_ms: 9999\n")
        cfg = load_config()
        assert cfg.database.busy_timeout_ms == 9999
        # Other database fields should still be defaults.
        assert cfg.database.wal is True

    def test_explicit_path_override(self, tmp_path: Path, fake_home: Path) -> None:
        custom = tmp_path / "custom.yaml"
        custom.write_text("logging:\n  level: WARNING\n")
        cfg = load_config(path=custom)
        assert cfg.logging.level == "WARNING"


@pytest.mark.unit
class TestEnvOverrides:
    def test_env_log_level(self, fake_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NAYRAASTRA_LOGGING__LEVEL", "ERROR")
        cfg = load_config()
        assert cfg.logging.level == "ERROR"

    def test_env_nested_bool(self, fake_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NAYRAASTRA_DATABASE__WAL", "false")
        cfg = load_config()
        assert cfg.database.wal is False

    def test_env_int_value(self, fake_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NAYRAASTRA_EXECUTION__MAX_PARALLEL_TASKS", "8")
        cfg = load_config()
        assert cfg.execution.max_parallel_tasks == 8


@pytest.mark.unit
class TestValidationErrors:
    def test_invalid_yaml_raises_config_error(self, tmp_path: Path, fake_home: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("logging: {\n  unclosed brace\n")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_config(path=bad)

    def test_unknown_key_rejected(self, tmp_path: Path, fake_home: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("completely_unknown_key: 42\n")
        with pytest.raises(ConfigError):
            load_config(path=bad)

    def test_invalid_log_level_rejected(self, tmp_path: Path, fake_home: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("logging:\n  level: VERBOSE\n")
        with pytest.raises(ConfigError):
            load_config(path=bad)

    def test_disruptive_without_flag_rejected(self, tmp_path: Path, fake_home: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("safety:\n  max_intrusiveness: disruptive\n  disruptive_enabled: false\n")
        with pytest.raises(ConfigError):
            load_config(path=bad)

    def test_non_mapping_yaml_rejected(self, tmp_path: Path, fake_home: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("- item1\n- item2\n")
        with pytest.raises(ConfigError):
            load_config(path=bad)
