"""Polling performance instrumentation and conservative benchmark evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from morningstar_modbus.models import ModbusExchange


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _frame_size(hex_payload: str) -> int:
    return len(hex_payload) // 2


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def estimate_rtu_wire_time_ms(
    *,
    request_bytes: int,
    response_bytes: int,
    request_count: int,
    baudrate: int,
    stop_bits: int,
) -> float:
    """Estimate RTU bus occupancy including conservative 3.5-character gaps per exchange."""
    if baudrate <= 0 or request_count <= 0:
        return 0.0
    bits_per_character = 1 + 8 + stop_bits  # start + data + stop; parity is disabled
    frame_bits = (request_bytes + response_bytes) * bits_per_character
    silent_gap_bits = request_count * 7.0 * bits_per_character
    return (frame_bits + silent_gap_bits) / baudrate * 1000.0


@dataclass(frozen=True, slots=True)
class PollPerformanceSample:
    observed_at: str
    transport: str
    configured_interval_seconds: float
    poll_latency_ms: float
    request_count: int
    successful_requests: int
    failed_requests: int
    request_bytes: int
    response_bytes: int
    estimated_wire_time_ms: float | None
    bus_utilization_percent: float | None
    deadline_missed: bool
    success: bool
    error: str = ""

    @property
    def total_bytes(self) -> int:
        return self.request_bytes + self.response_bytes

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["total_bytes"] = self.total_bytes
        return payload


class PollTrafficTracker:
    """Collect Modbus exchanges belonging to one logical profile poll."""

    def __init__(
        self,
        transport: str,
        *,
        baudrate: int | None = None,
        stop_bits: int = 2,
    ) -> None:
        self.transport = transport
        self.baudrate = baudrate
        self.stop_bits = stop_bits
        self._lock = Lock()
        self._exchanges: list[ModbusExchange] = []

    def begin(self) -> None:
        with self._lock:
            self._exchanges.clear()

    def record(self, exchange: ModbusExchange) -> None:
        with self._lock:
            self._exchanges.append(exchange)

    def finish(
        self,
        *,
        configured_interval_seconds: float,
        poll_latency_ms: float,
        success: bool,
        error: str = "",
    ) -> PollPerformanceSample:
        with self._lock:
            exchanges = tuple(self._exchanges)
        request_bytes = sum(_frame_size(item.request_hex) for item in exchanges)
        response_bytes = sum(_frame_size(item.response_hex) for item in exchanges)
        successful_requests = sum(1 for item in exchanges if not item.error_type)
        failed_requests = len(exchanges) - successful_requests
        wire_time_ms: float | None = None
        bus_utilization: float | None = None
        if self.transport == "serial" and self.baudrate:
            wire_time_ms = estimate_rtu_wire_time_ms(
                request_bytes=request_bytes,
                response_bytes=response_bytes,
                request_count=len(exchanges),
                baudrate=self.baudrate,
                stop_bits=self.stop_bits,
            )
            if configured_interval_seconds > 0:
                bus_utilization = wire_time_ms / (configured_interval_seconds * 1000.0) * 100.0
        return PollPerformanceSample(
            observed_at=utcnow(),
            transport=self.transport,
            configured_interval_seconds=configured_interval_seconds,
            poll_latency_ms=poll_latency_ms,
            request_count=len(exchanges),
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            estimated_wire_time_ms=wire_time_ms,
            bus_utilization_percent=bus_utilization,
            deadline_missed=poll_latency_ms > configured_interval_seconds * 1000.0,
            success=success,
            error=error[:1000],
        )


@dataclass(frozen=True, slots=True)
class BenchmarkThresholds:
    min_success_rate: float = 0.98
    max_p95_interval_ratio: float = 0.80
    max_deadline_miss_rate: float = 0.05
    max_request_failure_rate: float = 0.02
    max_bus_utilization_percent: float = 70.0


@dataclass(frozen=True, slots=True)
class BenchmarkStage:
    interval_seconds: float
    passed: bool
    summary: dict[str, Any]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "interval_seconds": self.interval_seconds,
            "passed": self.passed,
            "summary": self.summary,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class PollingBenchmarkReport:
    profile: str
    transport: str
    stages: tuple[BenchmarkStage, ...]
    recommended_interval_seconds: float | None
    fastest_tested_interval_seconds: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "transport": self.transport,
            "recommended_interval_seconds": self.recommended_interval_seconds,
            "fastest_tested_interval_seconds": self.fastest_tested_interval_seconds,
            "stages": [stage.to_dict() for stage in self.stages],
        }


def summarize_performance(samples: list[PollPerformanceSample]) -> dict[str, Any]:
    if not samples:
        return {
            "samples": 0,
            "success_rate": 0.0,
            "poll_rate_hz": 0.0,
            "poll_latency_p50_ms": None,
            "poll_latency_p95_ms": None,
            "poll_latency_p99_ms": None,
            "deadline_misses": 0,
            "deadline_miss_rate": 0.0,
            "request_count": 0,
            "request_failure_rate": 0.0,
            "modbus_requests_per_second": 0.0,
            "modbus_bytes_per_second": 0.0,
            "bus_utilization_percent": None,
            "bus_utilization_max_percent": None,
        }

    latencies = [sample.poll_latency_ms for sample in samples]
    success_count = sum(sample.success for sample in samples)
    deadline_misses = sum(sample.deadline_missed for sample in samples)
    request_count = sum(sample.request_count for sample in samples)
    failed_requests = sum(sample.failed_requests for sample in samples)
    total_bytes = sum(sample.total_bytes for sample in samples)
    bus_values = [
        sample.bus_utilization_percent
        for sample in samples
        if sample.bus_utilization_percent is not None
    ]

    timestamps = []
    for sample in samples:
        try:
            timestamps.append(datetime.fromisoformat(sample.observed_at.replace("Z", "+00:00")))
        except ValueError:
            pass
    duration_seconds = 0.0
    if len(timestamps) >= 2:
        duration_seconds = max((max(timestamps) - min(timestamps)).total_seconds(), 0.0)
    poll_rate = (len(samples) - 1) / duration_seconds if duration_seconds > 0 else 0.0
    request_rate = request_count / duration_seconds if duration_seconds > 0 else 0.0
    byte_rate = total_bytes / duration_seconds if duration_seconds > 0 else 0.0

    return {
        "samples": len(samples),
        "success_rate": success_count / len(samples),
        "poll_rate_hz": poll_rate,
        "poll_latency_p50_ms": percentile(latencies, 0.50),
        "poll_latency_p95_ms": percentile(latencies, 0.95),
        "poll_latency_p99_ms": percentile(latencies, 0.99),
        "deadline_misses": deadline_misses,
        "deadline_miss_rate": deadline_misses / len(samples),
        "request_count": request_count,
        "request_failure_rate": failed_requests / request_count if request_count else 0.0,
        "modbus_requests_per_second": request_rate,
        "modbus_bytes_per_second": byte_rate,
        "bus_utilization_percent": sum(bus_values) / len(bus_values) if bus_values else None,
        "bus_utilization_max_percent": max(bus_values) if bus_values else None,
    }


def evaluate_benchmark_stage(
    interval_seconds: float,
    samples: list[PollPerformanceSample],
    thresholds: BenchmarkThresholds,
) -> BenchmarkStage:
    summary = summarize_performance(samples)
    reasons: list[str] = []
    if summary["success_rate"] < thresholds.min_success_rate:
        reasons.append("poll success rate below threshold")
    p95 = summary["poll_latency_p95_ms"]
    if p95 is None or p95 > interval_seconds * 1000.0 * thresholds.max_p95_interval_ratio:
        reasons.append("p95 poll latency leaves insufficient interval headroom")
    if summary["deadline_miss_rate"] > thresholds.max_deadline_miss_rate:
        reasons.append("deadline-miss rate above threshold")
    if summary["request_failure_rate"] > thresholds.max_request_failure_rate:
        reasons.append("Modbus request failure rate above threshold")
    bus = summary["bus_utilization_max_percent"]
    if bus is not None and bus > thresholds.max_bus_utilization_percent:
        reasons.append("estimated RTU bus utilization above threshold")
    return BenchmarkStage(interval_seconds, not reasons, summary, tuple(reasons))


def build_benchmark_report(
    *,
    profile: str,
    transport: str,
    stages: list[BenchmarkStage],
) -> PollingBenchmarkReport:
    recommended: float | None = None
    fastest: float | None = None
    for stage in stages:
        fastest = stage.interval_seconds
        if stage.passed:
            recommended = stage.interval_seconds
        else:
            break
    return PollingBenchmarkReport(
        profile=profile,
        transport=transport,
        stages=tuple(stages),
        recommended_interval_seconds=recommended,
        fastest_tested_interval_seconds=fastest,
    )
