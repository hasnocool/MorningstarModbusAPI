"""Polling performance instrumentation and conservative benchmark evaluation."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Callable

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


class PollPersistenceLimiter:
    """Rate-limit poll-driven persistence while allowing faster in-memory polling."""

    def __init__(
        self,
        interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("persistence interval must be positive")
        self.interval_seconds = interval_seconds
        self._clock = clock
        self._last_write: dict[str, float] = {}

    def should_persist(self, controller_id: str) -> bool:
        now = self._clock()
        previous = self._last_write.get(controller_id)
        if previous is not None and now - previous < self.interval_seconds:
            return False
        self._last_write[controller_id] = now
        return True

    def forget(self, controller_id: str) -> None:
        self._last_write.pop(controller_id, None)


class AutoPollIntervalController:
    """Select a safe global watcher interval from live full-profile poll evidence.

    Auto mode deliberately reuses the same staged benchmark criteria as the CLI.
    It starts at the slowest configured benchmark stage, collects a complete sample
    window for every currently-present controller, and only then tries the next
    faster stage. If a stage fails it locks to the last passing stage. If the first
    stage fails, the configured conservative fallback is used.
    """

    def __init__(
        self,
        intervals_seconds: list[float] | tuple[float, ...],
        *,
        samples_per_interval: int,
        thresholds: BenchmarkThresholds,
        fallback_interval_seconds: float,
    ) -> None:
        intervals = tuple(sorted({float(value) for value in intervals_seconds}, reverse=True))
        if not intervals:
            raise ValueError("auto polling requires at least one interval")
        if samples_per_interval < 3:
            raise ValueError("auto polling requires at least three samples per interval")
        if fallback_interval_seconds < intervals[0]:
            raise ValueError("auto polling fallback must be at least as slow as the first interval")
        self.intervals_seconds = intervals
        self.samples_per_interval = samples_per_interval
        self.thresholds = thresholds
        self.fallback_interval_seconds = float(fallback_interval_seconds)
        self._stage_index = 0
        self._last_safe_interval: float | None = None
        self._locked_interval: float | None = None
        self._samples: dict[str, list[PollPerformanceSample]] = {}

    @property
    def current_interval_seconds(self) -> float:
        if self._locked_interval is not None:
            return self._locked_interval
        return self.intervals_seconds[self._stage_index]

    @property
    def calibrating(self) -> bool:
        return self._locked_interval is None

    def reset(self) -> None:
        self._stage_index = 0
        self._last_safe_interval = None
        self._locked_interval = None
        self._samples.clear()

    def observe(
        self,
        samples: dict[str, PollPerformanceSample],
        controller_ids: set[str],
    ) -> str | None:
        if self._locked_interval is not None or not controller_ids:
            return None

        for controller_id in controller_ids:
            sample = samples.get(controller_id)
            if sample is not None:
                self._samples.setdefault(controller_id, []).append(sample)

        if any(
            len(self._samples.get(controller_id, ())) < self.samples_per_interval
            for controller_id in controller_ids
        ):
            return None

        interval = self.current_interval_seconds
        failures: list[str] = []
        for controller_id in sorted(controller_ids):
            stage_samples = self._samples[controller_id][-self.samples_per_interval :]
            stage = evaluate_benchmark_stage(interval, stage_samples, self.thresholds)
            if not stage.passed:
                failures.append(f"{controller_id}: {', '.join(stage.reasons)}")
        self._samples.clear()

        if failures:
            selected = self._last_safe_interval or self.fallback_interval_seconds
            self._locked_interval = selected
            return (
                f"auto polling stopped at {interval:g}s; using {selected:g}s because "
                + "; ".join(failures)
            )

        self._last_safe_interval = interval
        if self._stage_index + 1 < len(self.intervals_seconds):
            next_interval = self.intervals_seconds[self._stage_index + 1]
            self._stage_index += 1
            return f"auto polling stage {interval:g}s passed; testing {next_interval:g}s"

        self._locked_interval = interval
        return f"auto polling selected {interval:g}s after all configured stages passed"


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
