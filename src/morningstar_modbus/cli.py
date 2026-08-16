# src/morningstar_modbus/cli.py
"""Command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

import uvicorn

from morningstar_modbus.api import create_app
from morningstar_modbus.capture import CaptureRecorder, load_capture_manifest, write_capture_bundle
from morningstar_modbus.catalog import get_profile
from morningstar_modbus.config import AppConfig, load_config
from morningstar_modbus.controller_scope import ControllerRegistry
from morningstar_modbus.discovery import discover
from morningstar_modbus.intelligence import refresh_intelligence, resolve_device_intelligence
from morningstar_modbus.intelligence.models import DeviceIntelligence
from morningstar_modbus.models import (
    DeviceIdentification,
    DiscoveredDevice,
    Endpoint,
    ModbusExchange,
)
from morningstar_modbus.polling import (
    BenchmarkThresholds,
    PollTrafficTracker,
    build_benchmark_report,
    evaluate_benchmark_stage,
)
from morningstar_modbus.polling_storage import PollingPerformanceStore
from morningstar_modbus.replay import ReplayModbusClient
from morningstar_modbus.storage import TelemetryStore
from morningstar_modbus.transport import AsyncModbusRtuClient, AsyncModbusTcpClient, ReadOnlyModbusClient
from morningstar_modbus.verification import verify_device
from morningstar_modbus.watcher import Watcher


def _endpoint_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--device", required=True, help="Serial device path or TCP host")
    parser.add_argument(
        "--transport",
        choices=("serial", "tcp"),
        help="Infer from --device when omitted",
    )
    parser.add_argument("--unit-id", type=int, default=1)
    parser.add_argument("--tcp-port", type=int, default=502)
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--stop-bits", type=int, choices=(1, 2), default=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="morningstar-modbus")
    parser.add_argument("--config", help="TOML configuration file")
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("discover", help="Probe configured serial ports and TCP hosts/subnets")

    read = sub.add_parser("read", help="Perform one raw read without writing to the database")
    read.add_argument("--transport", choices=("serial", "tcp"), required=True)
    read.add_argument("--target", required=True, help="Serial device path or TCP host")
    read.add_argument("--unit-id", type=int, default=1)
    read.add_argument("--address", type=lambda value: int(value, 0), required=True)
    read.add_argument("--count", type=int, default=1)
    read.add_argument("--function", choices=("holding", "input"), default="holding")
    read.add_argument("--tcp-port", type=int, default=502)
    read.add_argument("--baudrate", type=int, default=9600)
    read.add_argument("--stop-bits", type=int, choices=(1, 2), default=2)

    capture = sub.add_parser(
        "capture",
        help="Capture one read-only hardware session for replay",
    )
    _endpoint_arguments(capture)
    capture.add_argument("--output", default="capture", help="Capture bundle directory")
    capture.add_argument(
        "--include-identifiers",
        action="store_true",
        help=(
            "Keep structured target/serial identifiers; raw frames may contain identifiers "
            "regardless"
        ),
    )

    verify = sub.add_parser(
        "verify",
        help="Verify one attached device against its catalog profile",
    )
    _endpoint_arguments(verify)
    verify.add_argument("--json", action="store_true", help="Emit the report as JSON")
    verify.add_argument(
        "--capture",
        help="Also write the verification exchange stream to this directory",
    )

    replay = sub.add_parser(
        "replay",
        help="Run hardware verification against a capture bundle",
    )
    replay.add_argument("bundle", help="Capture bundle directory")
    replay.add_argument("--json", action="store_true")

    benchmark = sub.add_parser(
        "benchmark-polling",
        help="Measure safe full-profile polling intervals without Modbus writes",
    )
    _endpoint_arguments(benchmark)
    benchmark.add_argument(
        "--interval",
        dest="intervals",
        action="append",
        type=float,
        help="Interval in seconds; repeat to override configured benchmark stages",
    )
    benchmark.add_argument(
        "--samples",
        type=int,
        help="Samples per interval; defaults to [poll_benchmark].samples_per_interval",
    )
    benchmark.add_argument("--json", action="store_true", help="Emit JSON report")
    benchmark.add_argument(
        "--no-persist",
        action="store_true",
        help="Do not save benchmark performance samples to the configured database",
    )

    sub.add_parser("watch", help="Continuously discover, poll, and persist devices")
    sub.add_parser("serve", help="Serve the database over HTTP without polling")
    sub.add_parser("run", help="Run watcher and HTTP API in the same process")
    return parser


def _endpoint_from_args(args: argparse.Namespace) -> Endpoint:
    transport = args.transport
    if transport is None:
        device = str(args.device)
        transport = "serial" if device.startswith(("/dev/", "COM", "com")) else "tcp"
    if transport == "tcp":
        return Endpoint("tcp", args.device, args.unit_id, port=args.tcp_port)
    return Endpoint(
        "serial",
        args.device,
        args.unit_id,
        baudrate=args.baudrate,
        stop_bits=args.stop_bits,
    )


def _client_for_endpoint(
    config: AppConfig,
    endpoint: Endpoint,
    *,
    observer: Callable[[ModbusExchange], None] | None = None,
) -> ReadOnlyModbusClient:
    if endpoint.transport == "tcp":
        return AsyncModbusTcpClient(
            endpoint.target,
            port=endpoint.port or 502,
            unit_id=endpoint.unit_id,
            timeout=config.watch.request_timeout_seconds,
            observer=observer,
        )
    return AsyncModbusRtuClient(
        endpoint.target,
        baudrate=endpoint.baudrate or 9600,
        stop_bits=endpoint.stop_bits or 2,
        unit_id=endpoint.unit_id,
        timeout=config.watch.request_timeout_seconds,
        observer=observer,
    )


async def _discover(config: AppConfig) -> int:
    devices = await discover(config)
    payload = [
        {
            "endpoint": asdict(device.endpoint),
            "identity": device.identification.to_dict(),
            "profile": device.profile,
            "latency_ms": device.latency_ms,
        }
        for device in devices
    ]
    print(json.dumps(payload, indent=2))
    return 0


async def _read(config: AppConfig, args: argparse.Namespace) -> int:
    timeout = config.watch.request_timeout_seconds
    if args.transport == "tcp":
        client = AsyncModbusTcpClient(
            args.target,
            port=args.tcp_port,
            unit_id=args.unit_id,
            timeout=timeout,
        )
    else:
        client = AsyncModbusRtuClient(
            args.target,
            baudrate=args.baudrate,
            stop_bits=args.stop_bits,
            unit_id=args.unit_id,
            timeout=timeout,
        )
    try:
        values = (
            await client.read_input_registers(args.address, args.count)
            if args.function == "input"
            else await client.read_holding_registers(args.address, args.count)
        )
        print(
            json.dumps(
                {
                    "address": args.address,
                    "count": args.count,
                    "function": args.function,
                    "values": values,
                },
                indent=2,
            )
        )
        return 0
    finally:
        await client.close()


async def _capture(config: AppConfig, args: argparse.Namespace) -> int:
    endpoint = _endpoint_from_args(args)
    recorder = CaptureRecorder()
    client = _client_for_endpoint(config, endpoint, observer=recorder.record)
    try:
        try:
            identification = await client.read_device_identification()
        except Exception:
            identification = DeviceIdentification()
        intelligence = await resolve_device_intelligence(
            client,
            identification,
            endpoint=endpoint,
        )
        profile = get_profile(intelligence.profile)
        values = await profile.poll(client, firmware=intelligence.firmware)
        intelligence = refresh_intelligence(intelligence, values, endpoint=endpoint)
        bundle = write_capture_bundle(
            args.output,
            endpoint=endpoint,
            identification=identification,
            intelligence=intelligence,
            values=values,
            exchanges=recorder.exchanges,
            include_identifiers=args.include_identifiers,
        )
        print(str(bundle.resolve()))
        return 0
    finally:
        await client.close()


async def _verify(config: AppConfig, args: argparse.Namespace) -> int:
    endpoint = _endpoint_from_args(args)
    recorder = CaptureRecorder()
    client = _client_for_endpoint(config, endpoint, observer=recorder.record)
    try:
        report, identification, values = await verify_device(client, endpoint)
        if args.capture:
            intelligence = DeviceIntelligence(
                profile=report.profile,
                family=report.family,
                model=report.model,
                firmware=report.firmware,
                hardware_revision=report.hardware_revision,
                confidence=report.confidence,
                status=report.intelligence_status,
            )
            write_capture_bundle(
                args.capture,
                endpoint=endpoint,
                identification=identification,
                intelligence=intelligence,
                values=values,
                exchanges=recorder.exchanges,
            )
        print(json.dumps(report.to_dict(), indent=2) if args.json else report.render_text())
        return 0 if report.result == "verified" else 2
    finally:
        await client.close()


async def _replay(args: argparse.Namespace) -> int:
    manifest = load_capture_manifest(args.bundle)
    endpoint_data = manifest.get("endpoint", {})
    if not isinstance(endpoint_data, dict):
        raise ValueError("capture manifest endpoint must be an object")
    transport = str(endpoint_data.get("transport") or "tcp")
    endpoint = Endpoint(
        "serial" if transport == "serial" else "tcp",
        "replay",
        int(endpoint_data.get("unit_id") or 1),
        port=int(endpoint_data.get("port") or 502) if transport == "tcp" else None,
    )
    client = ReplayModbusClient.from_bundle(Path(args.bundle))
    try:
        report, _, _ = await verify_device(client, endpoint)
        print(json.dumps(report.to_dict(), indent=2) if args.json else report.render_text())
        return 0 if report.result == "verified" else 2
    finally:
        await client.close()


def _benchmark_intervals(config: AppConfig, args: argparse.Namespace) -> list[float]:
    intervals = args.intervals or config.poll_benchmark.intervals_seconds
    minimum = config.poll_benchmark.minimum_interval_seconds
    if not intervals:
        raise ValueError("at least one benchmark interval is required")
    if any(interval < minimum for interval in intervals):
        raise ValueError(f"benchmark intervals must be >= {minimum:g} seconds")
    return sorted(set(intervals), reverse=True)


def _render_benchmark(report: dict[str, object]) -> str:
    lines = [
        "Polling benchmark",
        f"profile: {report['profile']}",
        f"transport: {report['transport']}",
    ]
    for raw_stage in report["stages"]:
        stage = dict(raw_stage)
        summary = dict(stage["summary"])
        status = "PASS" if stage["passed"] else "STOP"
        p95 = summary.get("poll_latency_p95_ms")
        bus = summary.get("bus_utilization_max_percent")
        lines.append(
            f"{float(stage['interval_seconds']):.3f}s {status} "
            f"success={float(summary['success_rate']) * 100:.1f}% "
            f"p95={float(p95):.1f}ms " if p95 is not None else ""
        )
        if bus is not None:
            lines[-1] += f"bus_max={float(bus):.1f}%"
        reasons = stage.get("reasons", [])
        for reason in reasons:
            lines.append(f"  - {reason}")
    recommended = report.get("recommended_interval_seconds")
    lines.append(
        "recommended interval: "
        + (f"{float(recommended):.3f}s" if recommended is not None else "none from tested stages")
    )
    return "\n".join(lines)


async def _benchmark_polling(config: AppConfig, args: argparse.Namespace) -> int:
    endpoint = _endpoint_from_args(args)
    tracker = PollTrafficTracker(
        endpoint.transport,
        baudrate=(endpoint.baudrate or config.serial.baudrate)
        if endpoint.transport == "serial"
        else None,
        stop_bits=endpoint.stop_bits or config.serial.stop_bits,
    )
    client = _client_for_endpoint(config, endpoint, observer=tracker.record)
    performance_store: PollingPerformanceStore | None = None
    device_id: str | None = None
    try:
        try:
            identification = await client.read_device_identification()
        except Exception:
            identification = DeviceIdentification()
        intelligence = await resolve_device_intelligence(client, identification, endpoint=endpoint)
        profile = get_profile(intelligence.profile)
        await profile.poll(client, firmware=intelligence.firmware)  # warm-up, not measured

        if not args.no_persist:
            store = TelemetryStore(config.database.path)
            await store.initialize()
            registry = ControllerRegistry(config.database.path)
            await registry.initialize()
            device = DiscoveredDevice(endpoint, identification, 0.0, profile.name, intelligence)
            _controller_uid, device_id = await registry.register_observation(device)
            performance_store = PollingPerformanceStore(config.database.path)
            await performance_store.initialize()

        benchmark = config.poll_benchmark
        thresholds = BenchmarkThresholds(
            min_success_rate=benchmark.min_success_rate,
            max_p95_interval_ratio=benchmark.max_p95_interval_ratio,
            max_deadline_miss_rate=benchmark.max_deadline_miss_rate,
            max_request_failure_rate=benchmark.max_request_failure_rate,
            max_bus_utilization_percent=benchmark.max_bus_utilization_percent,
        )
        samples_per_interval = args.samples or benchmark.samples_per_interval
        if samples_per_interval < 3:
            raise ValueError("--samples must be >= 3")

        stages = []
        for interval in _benchmark_intervals(config, args):
            samples = []
            for _ in range(samples_per_interval):
                tracker.begin()
                started = time.perf_counter()
                success = True
                error = ""
                try:
                    await profile.poll(client, firmware=intelligence.firmware)
                except Exception as exc:
                    success = False
                    error = f"{type(exc).__name__}: {exc}"
                latency_ms = (time.perf_counter() - started) * 1000.0
                sample = tracker.finish(
                    configured_interval_seconds=interval,
                    poll_latency_ms=latency_ms,
                    success=success,
                    error=error,
                )
                samples.append(sample)
                if performance_store is not None and device_id is not None:
                    await performance_store.save(device_id, sample, mode="benchmark")
                elapsed = time.perf_counter() - started
                await asyncio.sleep(max(0.0, interval - elapsed))
            stage = evaluate_benchmark_stage(interval, samples, thresholds)
            stages.append(stage)
            if not stage.passed:
                break

        report = build_benchmark_report(
            profile=profile.name,
            transport=endpoint.transport,
            stages=stages,
        ).to_dict()
        print(json.dumps(report, indent=2) if args.json else _render_benchmark(report))
        return 0 if report["recommended_interval_seconds"] is not None else 2
    finally:
        await client.close()


async def _watch(config: AppConfig) -> int:
    store = TelemetryStore(config.database.path)
    await store.initialize()
    watcher = Watcher(config, store)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(watcher.stop()))
        except NotImplementedError:
            pass
    await watcher.run()
    return 0


async def _serve(config: AppConfig) -> int:
    store = TelemetryStore(config.database.path)
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(store, system_config=config.system, snmp_config=config.snmp),
            host=config.api.host,
            port=config.api.port,
            log_level="info",
        )
    )
    await server.serve()
    return 0


async def _run(config: AppConfig) -> int:
    store = TelemetryStore(config.database.path)
    await store.initialize()
    watcher = Watcher(config, store)
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(store, system_config=config.system, snmp_config=config.snmp),
            host=config.api.host,
            port=config.api.port,
            log_level="info",
        )
    )
    watcher_task = asyncio.create_task(watcher.run(), name="morningstar-watcher")
    server_task = asyncio.create_task(server.serve(), name="morningstar-api")
    done, pending = await asyncio.wait(
        {watcher_task, server_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    await watcher.stop()
    server.should_exit = True
    for task in pending:
        try:
            await task
        except asyncio.CancelledError:
            pass
    for task in done:
        exc = task.exception()
        if exc is not None:
            raise exc
    return 0


async def async_main(args: argparse.Namespace, config: AppConfig) -> int:
    if args.command == "discover":
        return await _discover(config)
    if args.command == "read":
        return await _read(config, args)
    if args.command == "capture":
        return await _capture(config, args)
    if args.command == "verify":
        return await _verify(config, args)
    if args.command == "replay":
        return await _replay(args)
    if args.command == "benchmark-polling":
        return await _benchmark_polling(config, args)
    if args.command == "watch":
        return await _watch(config)
    if args.command == "serve":
        return await _serve(config)
    return await _run(config)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = load_config(args.config)
    raise SystemExit(asyncio.run(async_main(args, config)))


if __name__ == "__main__":
    main()
