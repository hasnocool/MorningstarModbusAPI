"""Command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

import uvicorn

from morningstar_modbus.api import create_app
from morningstar_modbus.capture import CaptureRecorder, load_capture_manifest, write_capture_bundle
from morningstar_modbus.catalog import get_profile
from morningstar_modbus.config import AppConfig, load_config
from morningstar_modbus.discovery import discover
from morningstar_modbus.intelligence import refresh_intelligence, resolve_device_intelligence
from morningstar_modbus.intelligence.models import DeviceIntelligence
from morningstar_modbus.models import DeviceIdentification, Endpoint, ModbusExchange
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
            create_app(store),
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
            create_app(store),
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
