from datetime import UTC, datetime, timedelta

import httpx
import pytest

from morningstar_modbus.api import create_app
from morningstar_modbus.models import DeviceIdentification, DiscoveredDevice, Endpoint, ModbusExchange
from morningstar_modbus.polling import (
    BenchmarkThresholds,
    PollPerformanceSample,
    PollTrafficTracker,
    build_benchmark_report,
    evaluate_benchmark_stage,
    summarize_performance,
)
from morningstar_modbus.polling_storage import PollingPerformanceStore
from morningstar_modbus.storage import TelemetryStore


def _exchange(*, latency_ms: float = 20.0, error: str = "") -> ModbusExchange:
    return ModbusExchange(
        timestamp="2026-08-15T00:00:00+00:00",
        transport="serial",
        unit_id=1,
        function_code=3,
        address=0,
        count=80,
        request_hex="01030000005045fe",
        response_hex="01" + "03" + "a0" + ("00" * 160) + "1234",
        request_pdu_hex="0300000050",
        response_pdu_hex="03a0" + ("00" * 160),
        latency_ms=latency_ms,
        error_type="TimeoutError" if error else "",
        error=error,
    )


def _sample(
    observed_at: datetime,
    *,
    interval: float,
    latency_ms: float,
    success: bool = True,
    bus: float | None = 20.0,
) -> PollPerformanceSample:
    return PollPerformanceSample(
        observed_at=observed_at.isoformat(),
        transport="serial",
        configured_interval_seconds=interval,
        poll_latency_ms=latency_ms,
        request_count=1,
        successful_requests=1 if success else 0,
        failed_requests=0 if success else 1,
        request_bytes=8,
        response_bytes=165,
        estimated_wire_time_ms=bus * interval * 10.0 if bus is not None else None,
        bus_utilization_percent=bus,
        deadline_missed=latency_ms > interval * 1000.0,
        success=success,
        error="" if success else "TimeoutError: synthetic",
    )


def test_rtu_tracker_counts_frames_and_estimates_bus_utilization() -> None:
    tracker = PollTrafficTracker("serial", baudrate=9600, stop_bits=2)
    tracker.begin()
    tracker.record(_exchange())
    result = tracker.finish(
        configured_interval_seconds=1.0,
        poll_latency_ms=220.0,
        success=True,
    )

    assert result.request_count == 1
    assert result.successful_requests == 1
    assert result.request_bytes == 8
    assert result.response_bytes == 165
    assert result.estimated_wire_time_ms is not None
    assert result.bus_utilization_percent is not None
    assert 0 < result.bus_utilization_percent < 100
    assert not result.deadline_missed


def test_tcp_tracker_does_not_claim_serial_bus_utilization() -> None:
    tracker = PollTrafficTracker("tcp")
    tracker.begin()
    exchange = _exchange()
    tracker.record(
        ModbusExchange(
            timestamp=exchange.timestamp,
            transport="tcp",
            unit_id=1,
            function_code=3,
            address=0,
            count=80,
            request_hex=exchange.request_hex,
            response_hex=exchange.response_hex,
            request_pdu_hex=exchange.request_pdu_hex,
            response_pdu_hex=exchange.response_pdu_hex,
            latency_ms=20.0,
            error_type="",
            error="",
        )
    )
    result = tracker.finish(
        configured_interval_seconds=1.0,
        poll_latency_ms=50.0,
        success=True,
    )
    assert result.bus_utilization_percent is None
    assert result.estimated_wire_time_ms is None


def test_benchmark_stops_when_latency_headroom_is_exhausted() -> None:
    now = datetime(2026, 8, 15, tzinfo=UTC)
    safe = [_sample(now + timedelta(seconds=i), interval=1.0, latency_ms=200.0) for i in range(12)]
    fast = [
        _sample(now + timedelta(seconds=i / 4), interval=0.25, latency_ms=225.0, bus=55.0)
        for i in range(12)
    ]
    thresholds = BenchmarkThresholds()
    safe_stage = evaluate_benchmark_stage(1.0, safe, thresholds)
    fast_stage = evaluate_benchmark_stage(0.25, fast, thresholds)
    report = build_benchmark_report(
        profile="tristar_mppt",
        transport="serial",
        stages=[safe_stage, fast_stage],
    )

    assert safe_stage.passed
    assert not fast_stage.passed
    assert "p95 poll latency leaves insufficient interval headroom" in fast_stage.reasons
    assert report.recommended_interval_seconds == 1.0
    assert report.fastest_tested_interval_seconds == 0.25


def test_performance_summary_reports_rates_and_percentiles() -> None:
    now = datetime(2026, 8, 15, tzinfo=UTC)
    samples = [
        _sample(now + timedelta(seconds=i), interval=1.0, latency_ms=100.0 + i)
        for i in range(10)
    ]
    summary = summarize_performance(samples)

    assert summary["samples"] == 10
    assert summary["success_rate"] == 1.0
    assert summary["poll_rate_hz"] == pytest.approx(1.0)
    assert summary["poll_latency_p50_ms"] == pytest.approx(104.5)
    assert summary["modbus_requests_per_second"] > 0
    assert summary["modbus_bytes_per_second"] > 0


@pytest.mark.asyncio
async def test_polling_performance_store_and_api(tmp_path) -> None:
    database = tmp_path / "telemetry.db"
    telemetry = TelemetryStore(str(database))
    await telemetry.initialize()
    endpoint = Endpoint("tcp", "127.0.0.1", 1, port=502)
    identity = DeviceIdentification("Morningstar", "TriStar MPPT", "1.0")
    device_id = await telemetry.upsert_device(
        DiscoveredDevice(endpoint, identity, 1.0, "tristar_mppt")
    )

    performance_store = PollingPerformanceStore(str(database))
    await performance_store.initialize()
    now = datetime(2026, 8, 15, tzinfo=UTC)
    for i in range(5):
        await performance_store.save(
            device_id,
            _sample(
                now + timedelta(seconds=i),
                interval=1.0,
                latency_ms=150.0 + i,
                bus=None,
            ),
            mode="watch",
        )

    summary = await performance_store.summary(device_id, window=5)
    assert summary["samples"] == 5
    assert summary["poll_rate_hz"] == pytest.approx(1.0)
    assert summary["bus_utilization_percent"] is None

    app = create_app(telemetry)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/devices/polling/performance",
            params={"device_id": device_id, "window": 5},
        )
        history = await client.get(
            "/v1/devices/polling/history",
            params={"device_id": device_id, "limit": 5},
        )

    assert response.status_code == 200
    assert response.json()["samples"] == 5
    assert response.json()["poll_latency_p95_ms"] is not None
    assert history.status_code == 200
    assert len(history.json()) == 5
