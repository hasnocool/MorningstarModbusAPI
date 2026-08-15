"""TOML configuration loader."""

from __future__ import annotations

import ipaddress
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class DatabaseConfig:
    path: str = "./morningstar.db"


@dataclass(slots=True)
class WatchConfig:
    poll_interval_seconds: float = 5.0
    discovery_interval_seconds: float = 30.0
    request_timeout_seconds: float = 1.5
    unit_ids: list[int] = field(default_factory=lambda: [1])
    max_tcp_concurrency: int = 32
    failure_threshold: int = 3
    retry_backoff_initial_seconds: float = 2.0
    retry_backoff_max_seconds: float = 60.0


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
class ApiConfig:
    host: str = "127.0.0.1"
    port: int = 8080


@dataclass(slots=True)
class AppConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    watch: WatchConfig = field(default_factory=WatchConfig)
    serial: SerialConfig = field(default_factory=SerialConfig)
    tcp: TcpConfig = field(default_factory=TcpConfig)
    api: ApiConfig = field(default_factory=ApiConfig)


def load_config(path: str | None) -> AppConfig:
    if path is None:
        return AppConfig()
    payload = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    config = AppConfig(
        database=DatabaseConfig(**payload.get("database", {})),
        watch=WatchConfig(**payload.get("watch", {})),
        serial=SerialConfig(**payload.get("serial", {})),
        tcp=TcpConfig(**payload.get("tcp", {})),
        api=ApiConfig(**payload.get("api", {})),
    )
    _validate(config)
    return config


def _validate(config: AppConfig) -> None:
    if config.watch.poll_interval_seconds <= 0 or config.watch.discovery_interval_seconds <= 0:
        raise ValueError("watch intervals must be positive")
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
    for subnet in config.tcp.subnets:
        network = ipaddress.ip_network(subnet, strict=False)
        if network.num_addresses > 4096:
            raise ValueError(f"refusing TCP discovery network larger than /20: {subnet}")
