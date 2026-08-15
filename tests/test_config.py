import pytest

from morningstar_modbus.config import load_config


def _write_config(tmp_path, content: str):
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")
    return path


def test_config_accepts_auto_poll_interval(tmp_path) -> None:
    path = _write_config(
        tmp_path,
        """
[watch]
poll_interval_seconds = "auto"
""",
    )

    config = load_config(str(path))

    assert config.watch.poll_interval_seconds == "auto"


def test_config_accepts_numeric_subsecond_poll_interval(tmp_path) -> None:
    path = _write_config(
        tmp_path,
        """
[watch]
poll_interval_seconds = 0.2
""",
    )

    config = load_config(str(path))

    assert config.watch.poll_interval_seconds == pytest.approx(0.2)
    assert config.database.telemetry_write_interval_seconds == pytest.approx(1.0)


def test_config_rejects_unknown_poll_interval_string(tmp_path) -> None:
    path = _write_config(
        tmp_path,
        """
[watch]
poll_interval_seconds = "fast"
""",
    )

    with pytest.raises(ValueError, match='positive number or "auto"'):
        load_config(str(path))


def test_database_write_interval_cannot_be_faster_than_one_second(tmp_path) -> None:
    path = _write_config(
        tmp_path,
        """
[database]
telemetry_write_interval_seconds = 0.5
""",
    )

    with pytest.raises(ValueError, match="telemetry_write_interval_seconds must be >= 1.0"):
        load_config(str(path))


def test_auto_fallback_must_be_at_least_slowest_test_stage(tmp_path) -> None:
    path = _write_config(
        tmp_path,
        """
[poll_benchmark]
intervals_seconds = [2.0, 1.0, 0.5]
auto_fallback_interval_seconds = 1.0
""",
    )

    with pytest.raises(ValueError, match="auto_fallback_interval_seconds"):
        load_config(str(path))
