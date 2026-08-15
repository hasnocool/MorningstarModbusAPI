"""TOML configuration loader."""

from __future__ import annotations

import ipaddress
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypeAlias

PollInterval: TypeAlias = float | Literal["auto"]


@dataclass(slots=True)
class DatabaseConfig:
    path: str = "./morningstar.db"
    telemetry_write_interval_seconds: float = 1.0


@dataclass(slots=True)
class WatchConfig:
    poll_interval_seconds: PollInterval = 5.0
    discovery_interval_seconds: float = 30.0
    request_timeout_seconds: float = 1.5
    unit_ids: list[int] = field(default_factory=lambda: [1])
    max_tcp_concurrency: int = 32
    failure_threshold: int = 3
    retry_backoff_initial_seconds: float = 2.0
    retry_backoff_max_seconds: float = 60.0


@dataclass(slots=True)
class PollBenchmarkConfig:
    intervals_seconds: list[float] = field(default_factory=lambda: [1.0, 0.5, 0.25])
    samples_per_interval: int = 12
    min_success_rate: float = 0.98
    max_p95_interval_ratio: float = 0.80
    max_deadline_miss_rate: float = 0.05
    max_request_failure_rate: float = 0.02
    max_bus_utilization_percent: float = 70.0
    minimum_interval_seconds: float = 0.25
    auto_fallback_interval_seconds: float = 5.0


@dataclass(slots=True)
class SerialConfig:
    enabled: bool = True
    baudrate: int = 9600
    stop_bits: int = 2
    ports: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TcpConfig:
    enabled: bool = True
    port: int = 502
    hosts: list[str] = field(default_factory=list)
    subnets: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HistoryBackfillConfig:
    enabled: bool = True
    on_startup: bool = True
    on_reconnect: bool = True
    max_days: int = 200
    calendar_timezone: str = "local"
    http_port: int = 80
    http_path: str = "/datalog.html"
    timeout_seconds: float = 3.0
    max_response_bytes: int = 1_048_576


@dataclass(slots=True)
class ApiConfig:
    host: str = "127.0.0.1"
    port: int = 8080


@dataclass(slots=True)
class AppConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    watch: WatchConfig = field(default_factory=WatchConfig)
    poll_benchmark: PollBenchmarkConfig = field(default_factory=PollBenchmarkConfig)
    serial: SerialConfig = field(default_factory=SerialConfig)
    tcp: TcpConfig = field(default_factory=TcpConfig)
    backfill: HistoryBackfillConfig = field(default_factory=HistoryBackfillConfig)
    api: ApiConfig = field(default_factory=ApiConfig)


def load_config(path: str | None) -> AppConfig:
    if path is None:
        config = AppConfig()
        _validate(config)
        return config
    payload = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    config = AppConfig(
        database=DatabaseConfig(**payload.get("database", {})),
        watch=WatchConfig(**payload.get("watch", {})),
        poll_benchmark=PollBenchmarkConfig(**payload.get("poll_benchmark", {})),
        serial=SerialConfig(**payload.get("serial", {})),
        tcp=TcpConfig(**payload.get("tcp", {})),
        backfill=HistoryBackfillConfig(**payload.get("backfill", {})),
        api=ApiConfig(**payload.get("api", {})),
    )
    _validate(config)
    return config


def _normalize_poll_interval(value: object) -> PollInterval:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized != "auto":
            raise ValueError('watch.poll_interval_seconds must be a positive number or "auto"')
        return "auto"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('watch.poll_interval_seconds must be a positive number or "auto"')
    interval = float(value)
    if interval <= 0:
        raise ValueError("watch.poll_interval_seconds must be positive")
    return interval


def _validate(config: AppConfig) -> None:
    config.watch.poll_interval_seconds = _normalize_poll_interval(config.watch.poll_interval_seconds)
    if config.watch.discovery_interval_seconds <= 0:
        raise ValueError("watch discovery interval must be positive")
    if config.database.telemetry_write_interval_seconds < 1.0:
        raise ValueError("database.telemetry_write_interval_seconds must be >= 1.0")
    if not all(1 <= unit <= 247 for unit in config.watch.unit_ids):
        raise ValueError("unit_ids must be within 1..247")
    if not 1 <= config.watch.max_tcp_concurrency <= 256:
        raise ValueError("max_tcp_concurrency must be within 1..256")
    if config.watch.failure_threshold < 1:
        raise ValueError("failure_threshold must be positive")
    if config.watch.retry_backoff_initial_seconds <= 0:
        raise ValueError("retry_backoff_initial_seconds must be positive")
    if config.watch.retry_backoff_max_seconds < config.watch.retry_backoff_initial_seconds:
        raise ValueError("retry_backoff_max_seconds must be >= retry_backoff_initial_seconds")
    if not 1 <= config.backfill.max_days <= 200:
        raise ValueError("backfill.max_days must be within 1..200")
    if not config.backfill.calendar_timezone.strip():
        raise ValueError("backfill.calendar_timezone must not be empty")
    if not 1 <= config.backfill.http_port <= 65535:
        raise ValueError("backfill.http_port must be within 1..65535")
    if not config.backfill.http_path.startswith("/"):
        raise ValueError("backfill.http_path must start with /")
    if not config.backfill.http_path.isascii() or any(
        char in config.backfill.http_path for char in ("\r", "\n")
    ):
        raise ValueError("backfill.http_path must be ASCII and contain no line breaks")
    if config.backfill.timeout_seconds <= 0:
        raise ValueError("backfill.timeout_seconds must be positive")
    if not 16_384 <= config.backfill.max_response_bytes <= 8_388_608:
        raise ValueError("backfill.max_response_bytes must be between 16 KiB and 8 MiB")

    benchmark = config.poll_benchmark
    if benchmark.minimum_interval_seconds <= 0:
        raise ValueError("poll_benchmark.minimum_interval_seconds must be positive")
    if not benchmark.intervals_seconds:
        raise ValueError("poll_benchmark.intervals_seconds must not be empty")
    if any(interval < benchmark.minimum_interval_seconds for interval in benchmark.intervals_seconds):
        raise ValueError("poll benchmark interval is below minimum_interval_seconds")
    if benchmark.samples_per_interval < 3:
        raise ValueError("poll_benchmark.samples_per_interval must be >= 3")
    if benchmark.auto_fallback_interval_seconds <= 0:
        raise ValueError("poll_benchmark.auto_fallback_interval_seconds must be positive")
    if benchmark.auto_fallback_interval_seconds < max(benchmark.intervals_seconds):
        raise ValueError(
            "poll_benchmark.auto_fallback_interval_seconds must be >= the slowest benchmark interval"
        )
    for name, value in (
        ("min_success_rate", benchmark.min_success_rate),
        ("max_p95_interval_ratio", benchmark.max_p95_interval_ratio),
        ("max_deadline_miss_rate", benchmark.max_deadline_miss_rate),
        ("max_request_failure_rate", benchmark.max_request_failure_rate),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"poll_benchmark.{name} must be within 0..1")
    if not 0.0 < benchmark.max_bus_utilization_percent <= 100.0:
        raise ValueError("poll_benchmark.max_bus_utilization_percent must be within 0..100")

    for subnet in config.tcp.subnets:
        network = ipaddress.ip_network(subnet, strict=False)
        if network.num_addresses > 4096:
            raise ValueError(f"refusing TCP discovery network larger than /20: {subnet}")
